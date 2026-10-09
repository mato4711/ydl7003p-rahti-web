import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pytest
import analyzer_core as c


def result_for(y, x=None, **kw):
    if x is None:
        x=np.linspace(0,10,len(y))
    r=c.AnalysisResult(curve_xy=np.column_stack([x,y]),**kw)
    c.calculate_mechanical_properties(r,50,10,100,100)
    return r


def progressive(scale=1):
    x=np.linspace(0,10,501)
    return x,scale*np.where(x<=2, x/2,1-0.07*(x-2))


def test_progressive_metrics_and_rising_modulus():
    x,y=progressive();r=result_for(y,x)
    assert r.rupture_status=='no_clear_rupture'
    assert r.elongation_data is None and r.toughness_n_mm is None
    assert r.peak_strain_percent==pytest.approx(4)
    assert r.terminal_strain_percent==pytest.approx(20)
    assert r.maximum_stress_mpa==pytest.approx(1)
    assert r.residual_load_ratio==pytest.approx(.44)
    assert r.work_to_peak_n_mm==pytest.approx(1)
    assert r.post_peak_energy_n_mm==pytest.approx(5.76)
    assert r.work_to_terminal_n_mm==pytest.approx(6.76)
    assert r.elastic_modulus_mpa==pytest.approx(25)
    assert r.modulus_line[2]<=r.peak_extension_mm


@pytest.mark.parametrize('scale',[.05,1,100])
def test_clear_rupture_at_any_force_scale(scale):
    x=np.linspace(0,10,501)
    y=scale*np.where(x<4,x/4,0)
    r=result_for(y,x)
    assert r.rupture_status=='clear_rupture'
    assert 3.9<r.elongation_data<4.1
    assert r.toughness_n_mm is not None


def test_stop_drop_is_not_break_and_manual_override():
    x,y=progressive();y[x>=9.8]=0
    r=result_for(y,x,elongation=10,elongation_source='user edited')
    assert r.rupture_status=='uncertain' and r.elongation_data is None
    assert r.terminal_extension_mm<9.8
    r.rupture_mode='no_rupture';c.calculate_mechanical_properties(r,50,10,None,None)
    assert r.rupture_status=='no_rupture'
    assert r.maximum_stress_mpa is None and r.elastic_modulus_mpa is None
    assert r.residual_load_ratio>.4
    r.manual_terminal_extension=9.5;c.calculate_mechanical_properties(r,50,10,100,100)
    assert r.terminal_extension_mm==9.5
    assert r.residual_load_ratio==pytest.approx(.475)


def test_large_endpoint_drop_remains_uncertain():
    x=np.linspace(0,10,501);y=np.minimum(x/2,1);y[x>=9.8]=0
    r=result_for(y,x,elongation=10,elongation_source='user edited')
    assert r.rupture_status=='uncertain'
    r.rupture_mode='rupture';r.manual_break_extension=9.7
    c.calculate_mechanical_properties(r,50,10,100,100)
    assert r.rupture_status=='confirmed_rupture' and r.break_is_manual
    assert r.elongation_data==9.7


def test_zero_tail_gradual_softening_is_uncertain():
    x=np.linspace(0,10,501);y=np.where(x<2,x/2,(10-x)/8)
    r=result_for(y,x)
    assert r.rupture_status=='uncertain' and r.elongation_data is None


def test_tiny_transient_dip_and_recovery_is_not_rupture():
    x,y=progressive();y[200:202]=0;r=result_for(y,x)
    assert r.rupture_status=='no_clear_rupture'


def test_endpoint_interpolation_work_balance_and_deduplication():
    x,y=progressive();r=result_for(y,x,rupture_mode='no_rupture',manual_terminal_extension=7.333)
    assert r.terminal_extension_mm==7.333
    assert r.terminal_force_n==pytest.approx(1-.07*5.333)
    assert r.work_to_terminal_n_mm==r.work_to_peak_n_mm+r.post_peak_energy_n_mm
    r.curve_xy=np.vstack([r.curve_xy[::-1],r.curve_xy[:20],[np.nan,1]])
    c.calculate_mechanical_properties(r,50,10,100,100)
    assert r.terminal_force_n==pytest.approx(1-.07*5.333)


def test_baseline_after_instrument_endpoint_excluded():
    x,y=progressive();y[x>8]=0
    r=result_for(y,x,elongation=8,elongation_source='user edited',rupture_mode='no_rupture')
    assert r.terminal_extension_mm==8
    assert r.residual_load_ratio==pytest.approx(.58)


def test_no_initial_work_is_invented():
    x=np.linspace(1,10,451);y=np.where(x<2,x/2,1-.07*(x-2))
    r=result_for(y,x)
    assert r.work_to_peak_n_mm==pytest.approx(.75)
    assert 'initial unrecorded work is excluded' in r.mechanical_note


def test_low_force_axis_labels_supported(monkeypatch):
    # Three or more consistent 1-N labels must support the low-force scale.
    calls=iter([
        [(40,0,5,90,'5'),(80,0,10,90,'10')],
        [(0,20,10,90,'10'),(0,40,8,90,'8'),(0,60,6,90,'6'),(0,80,4,90,'4')],
    ])
    monkeypatch.setattr(c,'tesseract_tokens',lambda *args,**kw: next(calls))
    image=np.zeros((150,250,3),dtype=np.uint8)
    xmin,xmax,ymin,ymax=c.estimate_axis_limits(image,c.Rect(10,10,210,130))
    assert xmax==25 and ymax==12
