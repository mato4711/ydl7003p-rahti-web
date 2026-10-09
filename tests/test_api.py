import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pytest
from fastapi.testclient import TestClient
import app as web
import analyzer_core as c


@pytest.fixture
def session(tmp_path):
    sid='test-session'
    x=np.linspace(0,10,501);y=np.where(x<=2,x/2,1-.07*(x-2));y[x>=9.8]=0
    result=c.AnalysisResult(curve_xy=np.column_stack([x,y]),elongation=10,elongation_source='user edited',max_force=1)
    im=np.zeros((512,800,3),dtype=np.uint8)
    state={'id':sid,'dir':tmp_path,'source_name':'test.png','source_path':tmp_path/'test.png',
           'original':im,'rectified':im,'corners':np.array([[0,0],[799,0],[799,511],[0,511]]),
           'result':result,'gauge_length_mm':50.,'sample_width_mm':10.,'thickness_um':100.,'grammage_g_m2':100.}
    web._sessions[sid]=state;web._refresh_outputs(state)
    yield TestClient(web.app),sid,state
    web._sessions.pop(sid,None)


def test_outcome_metrics_and_exports(session):
    client,sid,state=session
    assert client.get('/health').json()['version']=='1.15'
    response=client.post(f'/api/session/{sid}/update',json={'rupture_mode':'no_rupture','manual_terminal_extension':9.5})
    assert response.status_code==200,response.text
    r=response.json()['result']
    assert r['rupture_status']=='no_rupture' and r['elongation_data'] is None
    assert r['terminal_strain_percent']==19
    assert r['maximum_stress_mpa']==pytest.approx(1)
    assert r['residual_load_ratio']==pytest.approx(.475)
    assert r['elastic_modulus_mpa']==pytest.approx(25)
    pdf=client.get(f'/api/session/{sid}/export/pdf')
    assert pdf.status_code==200 and pdf.content.startswith(b'%PDF')
    xlsx=client.get(f'/api/session/{sid}/export/xlsx')
    assert xlsx.status_code==200 and xlsx.content.startswith(b'PK')
    from io import BytesIO
    from zipfile import ZipFile
    xml=ZipFile(BytesIO(xlsx.content)).read('xl/worksheets/sheet1.xml').decode()
    assert 'Post-peak work' in xml and 'Terminal strain' in xml
    assert 'Extension at break from instrument' not in xml


def test_api_rejects_invalid_outcome_endpoint_and_geometry(session):
    client,sid,state=session
    for payload in [{'rupture_mode':'unknown'},{'manual_terminal_extension':-1},{'manual_terminal_extension':11},
                    {'manual_terminal_extension':'nan'},{'gauge_length_mm':-5}]:
        assert client.post(f'/api/session/{sid}/update',json=payload).status_code==400


def test_provisional_export_protection(session):
    client,sid,state=session;state['axis_confirmation_required']=True
    for kind in ['pdf','xlsx','png','csv']:
        assert client.get(f'/api/session/{sid}/export/{kind}').status_code==409
