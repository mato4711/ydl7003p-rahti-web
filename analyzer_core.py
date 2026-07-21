#!/usr/bin/env python3
"""
Mechanical tester screen rectifier, curve extractor, and mechanical analyser.

Features
--------
* Opens a mobile-phone photograph of a YDL-7003-P style tester screen.
* Finds the four display corners automatically from the blue UI region.
* Lets the user correct the four corners by dragging them in the original view.
* Perspective-corrects the screen to a rectangular image without downsampling.
* Shows the perspective-corrected screen as the main view; the original/corner editor opens on demand.
* Finds the Elong. and Maximum force result boxes and reads their values with a trained template matcher.
* Finds the force/elongation graph, estimates axis limits, and digitizes the green curve.
* Calculates break elongation, maximum force, elastic slope/modulus, and toughness.
* Draws a separate analysis graph: Force vs. elongation %, with the elastic fit line,
  break elongation markers, and a compact results table.
* Exports the perspective-corrected screen, curve CSV, a valid multi-sheet Excel .xlsx report, and a PDF report.
* Can learn new digit templates from user-corrected Elong. and Maximum force values.
* Displays instrument-output values consistently with two decimals.
* Uses ISO 527-style wording: extension at break [mm], tensile strain at break [%], maximum force, tensile modulus, and tensile energy.
* User-trained digit templates are normalized before saving to avoid shape-mismatch errors.
* Corner-adjustment windows use a crosshair cursor and magnifier for precise placement.

Dependencies
------------
    pip install opencv-python pillow numpy

Tesseract/pytesseract are optional. If installed, they are used only as an extra
axis-label OCR aid. The Elong. and Maximum force values are read with the built-in
template matcher, not with OCR.
"""

from __future__ import annotations

import base64
import csv
import io
import json
import math
import os
import re
import shutil
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

def trapezoid_integral(y, x):
    """Compatibility wrapper for NumPy 1.x and 2.x.

    NumPy 2.x removed np.trapz in some environments; np.trapezoid is the
    replacement. Older NumPy versions may not have np.trapezoid, so keep a
    fallback.
    """
    if hasattr(np, "trapezoid"):
        return np.trapezoid(y, x)
    return np.trapz(y, x)


from PIL import Image, ImageDraw, ImageFont

try:
    import pytesseract
    from pytesseract import Output
except ImportError:
    pytesseract = None
    Output = None



# Embedded template set trained from the supplied, distortion-corrected tester images.
# A file named digit_templates.npz in the same directory overrides this built-in set.
EMBEDDED_DIGIT_TEMPLATES_B64 = """
UEsDBC0AAAAIAAAAIQD+cTKr//////////8KABQAY2hhcl8wLm5weQEAEABgPgAAAAAAAKkCAAAAAAAA7di/jhMx
EAZw0/IU2y1IaUCHkHgAOhANBRWKuCAKxKEErjl4Ch7YHFJ0CM/3zXhsb9joZrrM/OJ1Nut/++v121dv3j1I1+lm
vtwdPuznF9P84/uTeTPNH6/23/bbL++v9pe7P/mX28+H3W3+8Gn7dXf7+dGzzfT86Wa6uHi8mX5OLfEwRYyIfBe1
zsBZhoNSDC3EWEJMKcCKLbFGSywr1KICwzhtJNnlxlqEGQUF2uwwm+6lzf/NytLZWkEH2bH9zSuwJ3jWXfMDnWrV
HOtco7WnZZglV0MN1/ziY4VS1/rmWTdd67GCpaUYUN++xLPfAVqhhbdkRMRZR/Vz3jHcfOO4/yzimXcYPdlZRKd8
bTmWmIWNYIuvV2Fx2rLWMj9kNe206R5bestarXXCbrUrumertrne5nqbLTtihoG2cd6xratnxhBAmHQMYdwvhHGv
qrDDpjIcdMQ5wLMpIBRhSgVX5V9us4iIiHWFHOh87KMCsbgN0+K0bRPI0hmsydqv5RBus6mMHsu7oFlBwy5rRWkp
ix5/YUXDPVbSVViKey3DiBILm8UW08bZE27tlT24SCy0X0/L2JIqWFKKEV1yu+6gxy+YIiIiYljUjszmIc+1Y4oi
05nrtYbrdUnXvA7zGJMmVMt6VkG1A4awssLv5F2tollZU6go1tiMPoUNG3YRC7955raoLWXV+YxYbdVzWO3bWoFh
mMeYNAHS2bpaLp9U3zovLMVSOo9ZC56ztFOxwm0XEXGyqHx6HeOia7xR7Rj1hLre7/QdXESFW1Qg2GoBJemPMJtt
tBUHF2npjQStcMqtpPQ8pD9R67HKbTh7u4b7G/9b2H+KChalTLEseOzguRqkPGtLTVZdGMy1MGdqyyVVo9raLajv
MEIwpL2HESqFVmVEVfwGUEsDBC0AAAAIAAAAIQCMcBVs//////////8KABQAY2hhcl8xLm5weQEAEADASgAAAAAA
ABwCAAAAAAAA7dg9TsNAEAVg03IKdwbJDSgCiQPQgWgoqJBFjCgQQQ7QAKfgwENQQETO/j2v1xknb7pE3yrxzKy1
s1+X1xdXN3vZW/ZeTOv5XVOc5cXH61FR5sX9rHlpqqfbWTOtf74/rx7n9eL7+UP1XC8+H5yU+elxmU8mh2X+mXeJ
/UxPiDuGsB6qwWpLmQ8jRc4A3LYuvW7tq1y2jRNZJ6WldVgN/avfMsFq/gItrXLrpC3ssRlAV7CfLnmYY2Qxb0mH
bUsTNhibddCIc7WT7syYpWJ2Qiw2Z4Gz03KBaZ3RWn4kle1tgFNoXZQ22jopLS3tKKyGd8l2vaMSzi2M/wDyBeQW
qQNQNKDAQDcAnQN0Wcfu7W0HiYTZtrNbkzRbs0xmgX8bb4E02LDFmlcheGMW2Ri0Q1k/paXdGYucCTKA0qqzQRSy
0JGW8RvYdKFkDOj3gCZprIRbCbcSbts0esAwOYu1UYO10nVrpzot8myQRfILWXDSMq+hpQ22Kq4yadVYSWQ1PNvY
bKpadK+bm4JXYthsipx/GX8BJA2uRe93CkA/II3WrX/7tF23Wx/bWEwRLqNHkdFZ7AiOWPMij4V6MtW+oFVpvVSF
VXG3TRthN9c8QjtKm753/BScLzhg4NGlGFv3gpBgKxJsJdxKuG1Tu12Tgw4NNjrgHb8Gi+QBHHIsC6zWsIK2b8ta
pLVIfmlpaeNs533soaOzKzyADhnfUEsDBC0AAAAIAAAAIQAGU50c//////////8KABQAY2hhcl8yLm5weQEAEADA
SgAAAAAAACkDAAAAAAAA7dnPbhMxEAbw5cpT7G1BygVUgcQDcKPiwoETimgQB0RRAr0AT8EDm1ZI1SYz33g+25Ns
qOfUOr/M+t96186fy3dv3r5/NNwMP6erze7jdno1Tr9+PJtW4/Tpevt9u/764Xp7tbkrf73+stvclu8+r79tbv9/
8mI1vny+Gi8unq7G32NJPB56VEeahV9muKBYaxRoQBUMpbCGFNi2ibEJW/llQ2JcXAquppThBosio9dzVvkI0jku
sAOkisVxZtboeoPmbCFl1iC/pNaqFlRIgjZIKmUMbVDVmP4nxl/YE9DytDaWwwC/m6P4MWRjhwVPJxufiy3q4HsM
vmVOkB49YoOZi+6J65/o+dsna+1XvKyFVGr5EcJquY7R5UwLGyGLcItFiaQSG/SwFrgGhTbbsro63BWobo4xiLdm
Y5ZnRffmZRBlNkN+GUPbVdVP5zUlqP/yzZISNV3S+OeuX3Ye0JSW3NkOGrNgLGLLwOwZouoQZYf9v/UhyA9Tjx4P
OOCdJUvzuwM9A7pchppH8dbGp8Aa6zq2gmqPSESjjtejLO7NGptSiC2l1OmmGx774FombXAcr8h6GtL8GoqlsI0o
MQEZWm6ZtEx11SDove6Wt9Rg1I57jx49zjX8tzmxgvjXG2ZxYlYy/7KHpcAmpay9SfLZTCF6Lc9Y0ArGqjVra9Fv
FDjHoTyznVPpKfcCXhvn5fb19+ep4Sxryz2bo+7r2xTJ0+4ck0JhSmHh1WUNTHqUyVqzcSHoAc9acybWWP0Ir4GN
OuT3N84e9f0fCXr0ePDhvXHqDhyZs8H6nQCxPGBq/UyQs/ITiNVyHeczKIW4EbIId04uLWclxlTm4a0mlfph6r9L
OIu7fpH29GmT37pp2gs/bSRLk8bQRklDappKs5oyiDIb8pBpXZyWOj74t/OblxtWD4KW/NaxBMv0A2WpjWGPHv9J
EBPbexMwdwxhidsQQFiIXqzrrL9qjNWDWaOYBS1oLMtsni6hvtE06g2EoMTLnT/nCWhy0+SmETlj6KE8fl2DJkB5
WuWN1GhZMkZbWCUIWmLD3pWjrAd7e9ieINTzssfC4y9QSwMELQAAAAgAAAAhAAXRQgf//////////woAFABjaGFy
XzMubnB5AQAQAOAMAAAAAAAA+wAAAAAAAADt1b0KwjAUBeC4+hTZopClUhB8ADfFxcFJio04iJVUXdSn8IFr3Vp6
T3oTW1w8mzefh9vgz2u5Xqw2A3ETd5WafGfVTKrHNVJaqn1mLzY5bTObms98nhxzU87zQ3I25etRpOV0omUcj7V8
ypAMxT8/SFGGYyrhS4cmJMI0pTGyhK6etGByDHBAA9iMUUt2wOtpWnyVzadzXHsnlrNwey9x8pXtqVb0QjkLFLWw
+vxre7N+mHFpXtqvWoRhhnV9DyD2sZ0vEW7db6yfBliAAyxniUZRu3UMcC3emPqYUTM0LtxT0EBshv71qOAnZlCI
KQowTQN+cLjun87zBlBLAwQtAAAACAAAACEAbd5Nv///////////CgAUAGNoYXJfNC5ucHkBABAAADIAAAAAAABJ
AgAAAAAAAO3YvU7DMBAH8GPlKbIFpCygSkg8ABuIhYEJVTSIAVGUAgvwFDxwKEJIjX0f/0vi0lLfRNxfrrYTbF8/
L67OL6/36JXeylm9uG3K06J8fzkqq6K8mzfPzfTxZt7M6u/2s+nDol62L+6nT/Xy+mBSFSfHVTGZHFbFR9En9inH
H0X7E7gEcLsa49k2jW3T2P70L2xIFRtR2cYUseZL2cmGWjJtt4+YJdu2rGVxOEuKjWYUsXzvVSrbqAeyZegYlqMj
WJZalm0F0lqWmQV+DFp4bPg+ITiVdXV47JkgLWDYxSbV14ddsuSgW2fJQXPkyJE8PMu/wzq2lYimOoQ7KHAGN8/r
QTbQkmXDPio2Go9s46EjlizLzKhkucm3bdQ2xHJUsCzlLTcwwQrUsOzXIWk9VpkaOQVv2/A61MxnsvbgbbNDzusO
KjwiCJswvUVoMruN5+p8Bs+RY4sDX6aVzX+QdewrfbcgT1r8VyvDtmlsSNdfOsV07ZahQO1kWZaa9ZDHWr9kBp9i
lr3UqGbD/in9jcYt23iORMtNp23lsUqdhSzX6LF2PcQNl8T3y0xhcchGj+j/WUyvTPHvH/zdpAYuSXhLTGvS9Nam
G2UB6qvenJVTjhw7Evg/UZIlyrH89lzUxysaBhQYidImqy82uBBIXzSQtWl1U4GWuZIsd6eWNbpV7mwCK3RfpeLu
zQ1asOz8GJZrRNIKY9OtVGCw5YFk+fDY+AEBFqDJ6xZXJxBPceBSus2iG3VaHt26juF+C1G/xajLEi5zrDm+AFBL
AwQtAAAACAAAACEAxmTeMP//////////CgAUAGNoYXJfNS5ucHkBABAAIFcAAAAAAAAkBAAAAAAAAO3YsW7UQBQF
0KXlK7ZbkLYBRYrEB9CBaCioUEQWUSCCNkADfAUfbIKAZD1z733vju3EC34VjM+MPeN5E7/98fzlsxev7q2+rL5u
zneXb/abJ+vNt8+PNtv15u3F/tP+7MPri/357lf707P3l7ur9st3Zx93V/9/cLpdnz7erk9OHm7X39ctcX+1xIDo
fsf1Pw4DUxzHbSXFtl5IsbhxkDmMZqcaOENXNp2TDbod2HCtr6/qHdYfLNiOkqJtmsaSFhhewZiMAVv5ROp2PmeB
K2oljGMnz8TFDrK0Y0HVXcpX3GLVWVC18FFREsWU2A5aiAkFuOuo7T1bV4SYc0g5BpRhSBEmEMwxDIMuscScovw4
Uru4A19HDGazXtER6oAUHs+2DmuMWp3MgsprZRjUOx6b7ETDWjZekdwb01Z+5iawsJPV552zfXs4pLBm8C1rq7Aa
oH+Bz7hol2/osL2EwsJwrKjW5mlB0vJ+lRW3Ka14pOp5ua3fBZ0reG1sYQAlWwS3wuaOWCePrfPB+gs72iklX1FA
vbLFrEWKDkIVOJZLLHGkkU83npsTfvE4dqI6oLkSaV8GsPqEankrNqK3YcNu2dcgrVkGTLd5W8uAxLe9Y0XNkCwD
6o82btnNQDudcdEu32Z5cQiemw2o+ABOWXojaUUK6Cl0kY32TqJRVaxlE7Ug2Cy0HbMOEK8ooN5RaZ3BGCOINZWl
lrDXISVVtTzMLrHE0UWVliL1xFkyYdHQbDUlFi4QfoRgZQ9thv4HNkV9m6OF1d0OafQ8N5fJ5kJW7sbDwdA+JhSH
Y2UCVU3UonZsycMhSyctemsMHHtkGk14bDujFL/TdWiwmZ6dbzNPZOxfuH0x7sAVYhElCYdbxRzk/WppFC716lCM
qFm4GHTFl4n7nFtiiTmFV0DzMOgcLJ6asQzGkhn0X7ajDzttKdL7w5+00T66uah24woIqTkdsWaoigZuQSuxeAzd
VlypWtRaFg2Atn2mZrBjp07bOXyvz8jKfh2y0QepbxVm+1fVF7GtqVdfYIyp/kEg+vWgE9Q6KTkGFGMIMaYU/iAT
xlJiLHF0YSQnp4N+J5XUsaMMW/dkMzPWNqZHaxP0qG20JmR/DS0Z1PZ17GTJlqgvEha2Y0seLRhA42ol26qAWSTi
ZFngHHRHa3nPkoq7VMOKRzIsmBnDaBHYwmhL0hAPkCgEOhl8yiEdoWRwDnciEea04Bre+JRbYonh0ZBDkHPq1QwG
He0zZjQ72rDBKvxpS7wzSLDVVP1IpGxEG21I52AblyzqgyjjzDq/yN1etg+zZLmAFdJLIOsVWx/ldxbG0xlTcaZt
WGc5J7LOOzWss1cMm9+sI/wAhrqydAH3oalVNYmMLdr6yY0/IDAl5w+S1uFqWECtPxyJSREs2V+cQP91/ARQSwME
LQAAAAgAAAAhAA9CIbX//////////woAFABjaGFyXzYubnB5AQAQAOAMAAAAAAAAIwEAAAAAAADtlj2OwjAQhUPL
KdwZpDRBSEh7gO1ANBRUKFqCKFaAEqABTsGBIUi7S+R5b+ygLDS8Ij8zn2aendjJeTQZjqetaB8d7DwrvnL7Yexx
l9jY2MU63+bparbO59kt/pl+F1kZL5bpJivvO0lsBr3Y9Pvd2JzMI2pHbzWgS6mfixD0rnBSoyXJYchimqCIreSq
JwSjMoTFHSHLzIGoz5knxFx4JzLAwW8yrGzIAJpgVbsvs6BOYCXJ3gzp4eJIYV1Uee8k6sIIYDCpg2DeUQb9IwG9
+IIFhV0UPH6OSlhBRbIGq1lws42z/zw2snNCv4+wQauxFquZkHU4LDOUBQniGD7SOqzWLOTrxNFKv/vRMztCCK33
qwE3Nipl09OL+9G/Bm89W1dQSwMELQAAAAgAAAAhAPmnGZP//////////woAFABjaGFyXzcubnB5AQAQAEAZAAAA
AAAAFQEAAAAAAADt17EKwjAQBuC4+hTZotBFKQg+gJvi4uAkxUYcxEqqLupT+MC1ImppJb2LTbnS/OBg/AzXO7Xx
PltM58sOO7OLCGW8VmLMxfU0EB4Xm0gdVbBfRSqUz/VJsItluh5vg4NMn/eGHh+lD9/ve/zGTdJlLrUmeSW38kNo
ApcfDKINtZg+oCwImwxO+9HAWz1FWHgFiFqtUExjzYegp8aNtXRlVRWLspa2JVACgeYS6AKBEiwNwnjbhg2iQssQ
FGUZxhZOTC4uLpaS/VLqfiqSsiDoV0Moib8BJIrAdBgwdBCt5fZc/6YEzkjtqKA6a2lbAkdVY2tp2z+s9raRf01D
bdnCpSBs/q2tHHBltoRmcSl9cxB0aVAeUEsDBC0AAAAIAAAAIQDHJPpk//////////8KABQAY2hhcl84Lm5weQEA
EAAAMgAAAAAAAIwCAAAAAAAA7dg7TsNAEAZg03IKdwbJDSgSEgegA9FQUKEIgigQoARogFNw4CWIV9j5/9kZe5MY
sVPBzGfvQ971Oq9HJ4fHpxvVY/XUXExm59Nmv26eH3aatm4ub6f30/HN2e30YvKePxhfzybz/OxqfDeZ/781auu9
3bYejbbb+qXuEptViQwRghkuhl1qHEiiiURaoTFWaYSjtM2ms8mupe4KK5yCErey1MUqnVhZHziVc2aYXz42VEhZ
lLRQ2GU2jCALICUrIuJRcA4ks5B6rKO39s1EgRHGeYxpe8odlEGkqahpNK4W+7etvgL8lmxQuIP8vqDJEEDSkw6E
us4Evr3PQX17FNGYAk1hiRIluoe2PfT4vkhQetZIYJg2WNxcb0tGnLQwn7ZZ++AYcYZsxxF/VkSCWBGVHVfdLP58
5rdd96d/MCw4401/YZC2WTYKmeKz47HxGfGPWP49n80qj5TDKpfTfIA42NOEut5DOd+FyrQnaJ4zOJBEE/mto79K
lCgxhDAvY/4etlCm++9RCIsaxzCPMWtOsbRnBuqyEhtmcgBWuTiTTf/a1tN6ngf2+scWfn7hxhYrtGN5fpdboeX9
zfaRIy4lFl8PKB+FgfI1hGxc0+hXlfaJ33jJltCV2iHMA8O/i6rFz8Py9mq6w6CWyNLC3Vqosetd20OmvQ9Qz2kH
cQ5LlPh/YVwW9gVnX53994de5xLPj0E6dVn2Oxe8GlvSFLKsXw4L0w7LJieR1M/aXotb+7GG+dWHTHsmK6xjohRH
1dnq2mFjuixrH5sqA31KPmocgzzBrLWUpaOQKWVy1mVlaQiWYzm2LDbolj999iTf7oMI1hoK2jWd+t6xmT4aJPUc
HxhnFEx1iWHGG1BLAwQtAAAACAAAACEA6F0p5P//////////CgAUAGNoYXJfOS5ucHkBABAAIFcAAAAAAAB8BAAA
AAAAAO3Yv24TQRAG8KPlKdwZJDegSJF4ADoQDQUViogRBQLkAA3wFDzwEKRE8e1833wzd+cQh53Ou7/bv7d7u/79
8vWLV28eDN+HH+vz7cW73frZav3z25P1ZrV+/3n3dXf26e3n3fn2b/rzs48X28v0iw9nX7aXvx+dblanTzerk5PH
m9Wv1ZR4OPS4u2FXkYb6gVYCbQFtsUW0wRbSMbaYjrAJuo9N0ZEFeQQ3Fo02mQI8NShxND6xbSZpmgW9GCi+b7Yy
DrE1aUnBJix5ddibBil7K+GaYvWhmGYTuoLpyAsq8OCiYvc0m06Ah4zFLSpQMG0JS2qKrd7OEq96XAKhYLX4FILb
4D1WNvt1U9jRAAOb+spHmkmgIzqwN65Hjx7HENGGNmOjjG1lsw7ODiCRWZSqqDqD027ElZEMRgGmxdasq5J27RZt
rnPSgpwlLOoJ6Z3BdFUAs+TKji2OSXbhiwAdTGWrh/uKbac7ttfC1UMsbNKCFlI9hD6xYulEisTEYpFjgNLpeFkY
vMuCLnUPqFwEAC1eBAo02GqCJ7Tp0aPHEURmyec3iPy+M3vvq/25UvpbMDptKxvR6JvlEyUl33RWH0pk3Qgr412O
G9Y0rk1q6UxLm3sP7KTxnXHyM2HZFYceE1tHLQnWtgXtknecdpYWOinC7XKUK+w1AE+KKFjZBkj966AtrQlkJKzs
AUzGmBSBkvEgQGzULnXJGVxUbOmOU7EYQwkxk+6hBOzR47gjuyjyiyi94hbYH+Yd7Sed7dHT2JKqJN3TCYowpSBL
2/bzhKgrJyjWFfxP7HBgawtbux0bzbFhq4+ivquYyrueAUuwhTY47Qd9iLZBU8FrjK3C0Ri1p/vWBvOU2T1Cyyoq
2ASt2DvQhCnNbZKSllYDGqDejkwHYDLGcQmpltlNNL99Jxa4XVSOMIQCzWWLQ9mjx/FH4XWfvuICXFj2eIuoXVyC
zzZ4VshRqqYD2ld1y8LHVcGAgixp3UkM2imXkQmWDRjKvUMW0xk2vBdWrDU2dRkh9SCqD67mrVpv44w4jZZxdbIz
o7Z2DSBA9/omm1i4U1M7+DmMLKmqQA9lM3Rec+mDfo55Pf51kNMYJ/EMgmGyb1YxFVP0LvrRgngcjpY+8kwXLKFA
c+keStEePXqw0Isovzpn7iaVvytKf4OUdspwBxY4pvJ0xTBMxlanwhJYywQt2fBTNsf6Gm/BDsom7pvIynEoWdqI
2OpJxthMWfiqM2tI8vpQkG4oKzEdIGWFHgq4tcXz3/7BWVpWS4FOs/hZZElFsNiEBYmJjoXP8zJUsW3L3E2ad9lF
NJQxrb1gBUo1pMULRoE2PHQ9evxPkV8Os9am/o9IYSKhPpANaKtBBsMwmWCVKC8ShVOf7AUfHZcSjOShrPxb7VA2
ul8cyi50F6G9nWBRhkFtiWQk+RpoXdM4lD0ds04ru9x5bt4G2E5qaK+fwI+GMc1KGpzNKzaxgko3aTLkcCqgNUhd
CeaC1RZKifnoKFq8vxZo4fTAOKMOc3ijhelxF+IPUEsDBC0AAAAIAAAAIQAYAKl2//////////8MABQAY2hhcl9k
b3QubnB5AQAQAEATAAAAAAAAWQEAAAAAAADVl7FOwzAURcPKV3gzSBloRz6ADcTSgQlFNIgBUZQUFspX8MGPdmgl
8LGfkzhueqUMPYvvu89+dn/uFrf3D2fFZ/Fll3X71NhrYzcfM1sa+7xq1k319rhqlvWO31Svbb3l7Uv1Xm9/X8zm
pZlf7b7L0nybHjovEkhEAP2HIg4UcaAEmYSYiAuHMFyXPB+oN6G88tn7A8OZYqiA9nAIGxr+pLIHgb1AZfHtiI0v
NQPTUJuawdHk96wMHQhaMrA+50PvyITkuoMqoDQllhTzCteIvZBO4rJwBd7AMJUWjKDzEBvSN2KeHtFm22Mtqizy
meMjg/04Icbjilt0HDlOaFcp2y/LWQgsocy1cL0Tk3e39BhNOd67Wj+Cng8YQohKa3SB5bjsKZdRs0/8FoCC+2aY
WHx9dLg/8ryB/UuoDCxDcR0iG1XgxGeZaxvtvRvLOPzQH0KoNyIpVb9QSwECLQMtAAAACAAAACEA/nEyq6kCAABg
PgAACgAAAAAAAAAAAAAAgAEAAAAAY2hhcl8wLm5weVBLAQItAy0AAAAIAAAAIQCMcBVsHAIAAMBKAAAKAAAAAAAA
AAAAAACAAeUCAABjaGFyXzEubnB5UEsBAi0DLQAAAAgAAAAhAAZTnRwpAwAAwEoAAAoAAAAAAAAAAAAAAIABPQUA
AGNoYXJfMi5ucHlQSwECLQMtAAAACAAAACEABdFCB/sAAADgDAAACgAAAAAAAAAAAAAAgAGiCAAAY2hhcl8zLm5w
eVBLAQItAy0AAAAIAAAAIQBt3k2/SQIAAAAyAAAKAAAAAAAAAAAAAACAAdkJAABjaGFyXzQubnB5UEsBAi0DLQAA
AAgAAAAhAMZk3jAkBAAAIFcAAAoAAAAAAAAAAAAAAIABXgwAAGNoYXJfNS5ucHlQSwECLQMtAAAACAAAACEAD0Ih
tSMBAADgDAAACgAAAAAAAAAAAAAAgAG+EAAAY2hhcl82Lm5weVBLAQItAy0AAAAIAAAAIQD5pxmTFQEAAEAZAAAK
AAAAAAAAAAAAAACAAR0SAABjaGFyXzcubnB5UEsBAi0DLQAAAAgAAAAhAMck+mSMAgAAADIAAAoAAAAAAAAAAAAA
AIABbhMAAGNoYXJfOC5ucHlQSwECLQMtAAAACAAAACEA6F0p5HwEAAAgVwAACgAAAAAAAAAAAAAAgAE2FgAAY2hh
cl85Lm5weVBLAQItAy0AAAAIAAAAIQAYAKl2WQEAAEATAAAMAAAAAAAAAAAAAACAAe4aAABjaGFyX2RvdC5ucHlQ
SwUGAAAAAAsACwBqAgAAhRwAAAAA
"""

# ----------------------------- Data structures ----------------------------- #

@dataclass
class Rect:
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return max(0, self.x2 - self.x1)

    @property
    def height(self) -> int:
        return max(0, self.y2 - self.y1)

    def clip(self, w: int, h: int) -> "Rect":
        return Rect(
            max(0, min(w - 1, self.x1)),
            max(0, min(h - 1, self.y1)),
            max(1, min(w, self.x2)),
            max(1, min(h, self.y2)),
        )

    def as_slice(self):
        return np.s_[self.y1:self.y2, self.x1:self.x2]


def rect_to_corners(rect: Rect) -> np.ndarray:
    """Return an axis-aligned Rect as TL, TR, BR, BL corner handles."""
    return np.array(
        [[rect.x1, rect.y1], [rect.x2, rect.y1], [rect.x2, rect.y2], [rect.x1, rect.y2]],
        dtype=np.float32,
    )


def corners_to_rect(corners: np.ndarray, width: int, height: int) -> Rect:
    """Convert dragged graph-corner handles to an axis-aligned plotting rectangle."""
    pts = np.asarray(corners, dtype=np.float32).reshape(-1, 2)
    x1 = int(round(float(np.nanmin(pts[:, 0]))))
    x2 = int(round(float(np.nanmax(pts[:, 0]))))
    y1 = int(round(float(np.nanmin(pts[:, 1]))))
    y2 = int(round(float(np.nanmax(pts[:, 1]))))
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    if x2 - x1 < 20 or y2 - y1 < 20:
        raise ValueError("The graph area is too small. Drag the handles to the plotting grid corners.")
    return Rect(x1, y1, x2, y2).clip(width, height)


def rect_to_norm(rect: Rect, width: int, height: int) -> list[float]:
    """Store graph area as normalized screen-relative coordinates."""
    return [
        rect.x1 / max(width, 1),
        rect.y1 / max(height, 1),
        rect.x2 / max(width, 1),
        rect.y2 / max(height, 1),
    ]


def norm_to_rect(norm: list[float] | tuple[float, float, float, float],
                 width: int, height: int) -> Rect:
    x1, y1, x2, y2 = [float(v) for v in norm[:4]]
    return Rect(
        int(round(x1 * width)),
        int(round(y1 * height)),
        int(round(x2 * width)),
        int(round(y2 * height)),
    ).clip(width, height)


@dataclass
class AnalysisResult:
    elong_box: Optional[Rect] = None
    maxforce_box: Optional[Rect] = None
    graph_plot: Optional[Rect] = None
    graph_corners: Optional[np.ndarray] = None
    elongation: Optional[float] = None
    max_force: Optional[float] = None
    elongation_source: str = ""
    max_force_source: str = ""
    x_min: float = 0.0
    x_max: float = 5.0
    y_min: float = 0.0
    y_max: float = 120.0
    curve_xy: Optional[np.ndarray] = None
    elongation_data: Optional[float] = None
    max_force_data: Optional[float] = None
    elongation_text_percent: Optional[float] = None
    elongation_data_percent: Optional[float] = None
    elastic_slope_n_per_mm: Optional[float] = None
    tensile_stiffness_kn_per_m: Optional[float] = None
    tensile_stiffness_index_knm_per_kg: Optional[float] = None
    elastic_modulus_mpa: Optional[float] = None
    modulus_r2: Optional[float] = None
    modulus_line: Optional[tuple[float, float, float, float]] = None
    break_line_x: Optional[float] = None
    toughness_n_mm: Optional[float] = None
    toughness_mj: Optional[float] = None
    mechanical_note: str = ""
    test_datetime: str = ""
    test_datetime_source: str = ""
    manual_break_extension: Optional[float] = None
    break_is_manual: bool = False


# ----------------------------- Image utilities ----------------------------- #

def order_quad(points: np.ndarray) -> np.ndarray:
    """Return four points as top-left, top-right, bottom-right, bottom-left."""
    pts = np.asarray(points, dtype=np.float32).reshape(4, 2)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array(
        [pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]],
        dtype=np.float32,
    )


def polygon_area(points: np.ndarray) -> float:
    p = np.asarray(points, dtype=np.float32)
    return float(abs(cv2.contourArea(p.reshape(-1, 1, 2))))


def detect_screen_corners(image_bgr: np.ndarray) -> np.ndarray:
    """
    Detect the LCD content area from the saturated blue interface.

    The blue UI occupies a large connected quadrilateral even when the black graph
    and white controls create holes. Morphological closing joins those regions,
    and the convex hull usually approximates directly to four corners.
    """
    h0, w0 = image_bgr.shape[:2]
    scale = min(1.0, 1600.0 / max(h0, w0))
    work = cv2.resize(image_bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(work, cv2.COLOR_BGR2HSV)

    # Main blue/cyan UI. This range is deliberately broad for different cameras.
    blue = cv2.inRange(hsv, np.array([78, 45, 45]), np.array([140, 255, 255]))

    short = min(work.shape[:2])
    k = max(9, int(round(short * 0.018)) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
    mask = cv2.morphologyEx(blue, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)),
        iterations=1,
    )

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    image_area = work.shape[0] * work.shape[1]
    candidates = []

    for c in contours:
        area = cv2.contourArea(c)
        if area < image_area * 0.04:
            continue
        hull = cv2.convexHull(c)
        peri = cv2.arcLength(hull, True)

        approx4 = None
        for eps in (0.018, 0.025, 0.035, 0.05, 0.07):
            a = cv2.approxPolyDP(hull, eps * peri, True)
            if len(a) == 4:
                approx4 = a.reshape(4, 2).astype(np.float32)
                break

        if approx4 is None:
            box = cv2.boxPoints(cv2.minAreaRect(hull))
            approx4 = box.astype(np.float32)

        q = order_quad(approx4)
        qw = (np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[3])) / 2
        qh = (np.linalg.norm(q[3] - q[0]) + np.linalg.norm(q[2] - q[1])) / 2
        aspect = qw / max(qh, 1.0)
        fill = area / max(polygon_area(q), 1.0)

        # The tested displays are landscape, typically around 1.5-2.0.
        aspect_score = math.exp(-((aspect - 1.72) / 0.65) ** 2)
        score = (area / image_area) * (0.55 + 0.45 * fill) * (0.45 + 0.55 * aspect_score)
        candidates.append((score, q))

    if not candidates:
        raise RuntimeError("Automatic screen detection failed. Use the whole-image corners and adjust them manually.")

    q = max(candidates, key=lambda item: item[0])[1] / scale

    # Slightly expand because the blue mask can stop one or two pixels inside the LCD.
    center = q.mean(axis=0)
    q = center + (q - center) * 1.012
    q[:, 0] = np.clip(q[:, 0], 0, w0 - 1)
    q[:, 1] = np.clip(q[:, 1], 0, h0 - 1)
    return order_quad(q)


def perspective_rectify(image_bgr: np.ndarray, corners: np.ndarray) -> np.ndarray:
    """
    Perspective-correct without reducing horizontal source resolution.

    The output width is at least the source photo width. Height follows the
    measured display aspect ratio. This avoids throwing away pixels from a
    close-up photograph and upscales distant-screen photographs.
    """
    q = order_quad(corners)
    top = np.linalg.norm(q[1] - q[0])
    bottom = np.linalg.norm(q[2] - q[3])
    left = np.linalg.norm(q[3] - q[0])
    right = np.linalg.norm(q[2] - q[1])

    measured_w = max(top, bottom)
    measured_h = max(left, right)
    aspect = measured_w / max(measured_h, 1.0)

    src_h, src_w = image_bgr.shape[:2]
    out_w = max(src_w, int(math.ceil(measured_w)))
    out_h = max(int(round(out_w / max(aspect, 0.2))), int(math.ceil(measured_h)))

    # Keep memory usage reasonable for unusually huge source files.
    max_pixels = 30_000_000
    if out_w * out_h > max_pixels:
        s = math.sqrt(max_pixels / (out_w * out_h))
        out_w = max(800, int(out_w * s))
        out_h = max(450, int(out_h * s))

    dst = np.array(
        [[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(q.astype(np.float32), dst)
    return cv2.warpPerspective(
        image_bgr,
        matrix,
        (out_w, out_h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def enhance_ocr_crop(crop_bgr: np.ndarray, mode: int = 0) -> np.ndarray:
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=3.5, fy=3.5, interpolation=cv2.INTER_CUBIC)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    if mode == 0:
        return cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    if mode == 1:
        return cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 41, 7
        )
    return cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)


def parse_number(text: str) -> Optional[float]:
    text = text.replace(",", ".")
    matches = re.findall(r"[-+]?(?:\d+\.\d+|\d+|\.\d+)", text)
    if not matches:
        return None
    try:
        return float(matches[0])
    except ValueError:
        return None


def normalize_decimal_text(text: str, decimal_places: int = 2) -> tuple[Optional[float], str]:
    """
    Convert OCR text into a number. The tester displays result values with two
    decimals, so OCR text like "198" becomes "1.98" and "5249" becomes "52.49".
    """
    s = text.strip().replace(",", ".")
    s = re.sub(r"[^0-9.\-]", "", s)
    if not s:
        return None, ""
    neg = s.startswith("-")
    s = s.replace("-", "")
    if "." in s:
        first = s.find(".")
        s = s[:first+1] + s[first+1:].replace(".", "")
    else:
        digits = re.sub(r"\D", "", s)
        if len(digits) > decimal_places:
            s = digits[:-decimal_places] + "." + digits[-decimal_places:]
        else:
            s = digits
    if neg:
        s = "-" + s
    try:
        return float(s), s
    except ValueError:
        return None, s


def color_number_masks(crop_bgr: np.ndarray, color: str) -> list[np.ndarray]:
    """
    Create binary images containing only the colored result digits. This is much
    more reliable than gray OCR on the whole rectangle because labels, grey
    button text, blue background and most reflections are removed.
    """
    if crop_bgr.size == 0:
        return []
    hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
    b, g, r = cv2.split(crop_bgr.astype(np.int16))
    masks: list[np.ndarray] = []

    if color == "green":
        masks.append(cv2.inRange(hsv, np.array([35, 45, 45]), np.array([95, 255, 255])))
        score = 2*g - r - b
        for thresh in (20, 35, 50):
            masks.append((score > thresh).astype(np.uint8) * 255)

    elif color == "purple":
        score = ((r + b) // 2) - g
        p = np.clip((score + 30) * 4, 0, 255).astype(np.uint8)
        masks.append(cv2.threshold(p, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1])
        for thresh in (6, 10, 14, 18, 24):
            masks.append((score > thresh).astype(np.uint8) * 255)
        masks.append(cv2.inRange(hsv, np.array([112, 18, 65]), np.array([178, 255, 255])))

    else:
        gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
        masks.append(cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1])

    cleaned = []
    for m in masks:
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        if cv2.countNonZero(m) > 20:
            cleaned.append(m)
    return cleaned


def prepare_mask_for_ocr(mask: np.ndarray, crop_to_content: bool) -> Optional[np.ndarray]:
    ys, xs = np.nonzero(mask)
    if len(xs) < 20:
        return None
    if crop_to_content:
        pad_x = max(8, int(mask.shape[1] * 0.025))
        pad_y = max(4, int(mask.shape[0] * 0.05))
        x1 = max(0, int(xs.min()) - pad_x)
        x2 = min(mask.shape[1], int(xs.max()) + pad_x + 1)
        y1 = max(0, int(ys.min()) - pad_y)
        y2 = min(mask.shape[0], int(ys.max()) + pad_y + 1)
        mask = mask[y1:y2, x1:x2]

    big = cv2.resize(mask, None, fx=4, fy=4, interpolation=cv2.INTER_NEAREST)
    big = cv2.dilate(big, np.ones((2, 2), np.uint8), iterations=1)
    border = max(10, big.shape[0] // 8)
    big = cv2.copyMakeBorder(big, border, border, border, border,
                             cv2.BORDER_CONSTANT, value=0)
    return big


def ocr_colored_number(crop_bgr: np.ndarray, color: str,
                       expected_range: tuple[float, float],
                       decimal_places: int = 2,
                       reference_value: Optional[float] = None) -> tuple[Optional[float], str, str]:
    """
    Read a colored numeric result value. A graph-derived reference value can be
    supplied for sanity checking, but OCR is still preferred when plausible.
    """
    if pytesseract is None:
        return None, "", "no pytesseract"

    candidates: list[tuple[float, float, str, str]] = []
    psm_modes = (7, 8, 13, 6)

    for mi, mask in enumerate(color_number_masks(crop_bgr, color)):
        crop_options = (False, True) if color == "purple" else (True, False)
        for crop_to_content in crop_options:
            proc = prepare_mask_for_ocr(mask, crop_to_content)
            if proc is None:
                continue
            for psm in psm_modes:
                for invert in (False, True):
                    img_for_ocr = 255 - proc if invert else proc
                    try:
                        txt = pytesseract.image_to_string(
                            img_for_ocr,
                            config=f"--oem 3 --psm {psm} -c tessedit_char_whitelist=0123456789.,-",
                            timeout=1.2,
                        )
                    except Exception:
                        continue
                    val, clean = normalize_decimal_text(txt, decimal_places)
                    if val is None:
                        continue
                    lo, hi = expected_range
                    if not (lo <= val <= hi):
                        continue

                    score = 20.0
                    raw = txt.strip().replace(" ", "")
                    if "." in raw or "," in raw:
                        score += 12.0
                    if len(re.sub(r"\D", "", raw)) >= 3:
                        score += 3.0
                    if not crop_to_content and color == "purple":
                        score += 4.0
                    if psm == 7:
                        score += 3.0

                    if reference_value is not None and reference_value > 0:
                        rel = abs(val - reference_value) / max(reference_value, 1e-6)
                        score += max(0.0, 18.0 * (1.0 - rel))
                        if val < 0.25 * reference_value:
                            score -= 25.0

                    candidates.append((score, val, clean, f"color {color}, mask {mi}, psm {psm}"))

    if candidates:
        candidates.sort(key=lambda z: z[0], reverse=True)
        score, val, clean, note = candidates[0]
        return val, clean, note

    return None, "", f"color {color} failed"


def ocr_single_number(crop_bgr: np.ndarray) -> tuple[Optional[float], str]:
    """Generic gray-scale Tesseract fallback."""
    if pytesseract is None:
        return None, "pytesseract not installed"

    candidates: list[tuple[float, str, float]] = []
    configs = [
        "--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789.,-",
        "--oem 3 --psm 8 -c tessedit_char_whitelist=0123456789.,-",
        "--oem 3 --psm 13 -c tessedit_char_whitelist=0123456789.,-",
    ]

    for mode in range(3):
        proc = enhance_ocr_crop(crop_bgr, mode)
        for cfg in configs:
            try:
                data = pytesseract.image_to_data(proc, config=cfg, output_type=Output.DICT, timeout=1.2)
                text_parts = []
                confs = []
                for t, c in zip(data["text"], data["conf"]):
                    if t.strip():
                        text_parts.append(t.strip())
                        try:
                            confs.append(float(c))
                        except Exception:
                            pass
                text = "".join(text_parts)
                value = parse_number(text)
                if value is not None:
                    conf = max(confs) if confs else 0.0
                    decimal_bonus = 10.0 if "." in text or "," in text else 0.0
                    candidates.append((conf + decimal_bonus, text, value))
            except Exception:
                continue

    if not candidates:
        return None, ""
    candidates.sort(key=lambda x: x[0], reverse=True)
    _, text, value = candidates[0]
    return value, text



def _valid_screen_date(value: str) -> Optional[str]:
    """Validate and normalize a YYYY/MM/DD value."""
    try:
        parsed = datetime.strptime(value, "%Y/%m/%d")
    except (TypeError, ValueError):
        return None
    if not (2000 <= parsed.year <= 2199):
        return None
    return parsed.strftime("%Y/%m/%d")


def _valid_screen_time(value: str) -> Optional[str]:
    """Validate and normalize a 24-hour HH:MM:SS value."""
    try:
        parsed = datetime.strptime(value, "%H:%M:%S")
    except (TypeError, ValueError):
        return None
    return parsed.strftime("%H:%M:%S")


def _datetime_candidates(text: str) -> tuple[list[str], list[str]]:
    """Extract valid date and time candidates from noisy OCR output."""
    compact = re.sub(r"\s+", "", text or "")
    dates: list[str] = []
    times: list[str] = []

    for match in re.findall(r"\d{4}/\d{2}/\d{2}", compact):
        value = _valid_screen_date(match)
        if value:
            dates.append(value)

    for match in re.findall(r"\d{2}:\d{2}:\d{2}", compact):
        value = _valid_screen_time(match)
        if value:
            times.append(value)

    # Fallback for OCR that drops separators but otherwise reads all digits.
    digit_runs = re.findall(r"\d+", compact)
    for run in digit_runs:
        if len(run) == 8:
            value = _valid_screen_date(f"{run[:4]}/{run[4:6]}/{run[6:8]}")
            if value:
                dates.append(value)
        if len(run) == 6:
            value = _valid_screen_time(f"{run[:2]}:{run[2:4]}:{run[4:6]}")
            if value:
                times.append(value)

    return dates, times


def detect_screen_datetime(rectified_bgr: np.ndarray) -> tuple[Optional[str], str]:
    """
    Read the tester timestamp from the light header at the top right.

    The expected display format is ``YYYY/MM/DD HH:MM:SS``. OCR is restricted
    to the small header regions and all candidates are validated as real dates
    and 24-hour times before they are accepted.
    """
    if pytesseract is None or rectified_bgr is None or rectified_bgr.size == 0:
        return None, "pytesseract unavailable"

    h, w = rectified_bgr.shape[:2]
    if h < 80 or w < 400:
        return None, "image too small"

    combined = rectified_bgr[
        0:max(12, int(round(0.080 * h))),
        int(round(0.700 * w)):min(w, int(round(0.997 * w))),
    ]
    date_crop = rectified_bgr[
        0:max(12, int(round(0.080 * h))),
        int(round(0.715 * w)):min(w, int(round(0.895 * w))),
    ]
    time_crop = rectified_bgr[
        0:max(12, int(round(0.080 * h))),
        int(round(0.875 * w)):min(w, int(round(0.997 * w))),
    ]

    date_scores: dict[str, float] = {}
    time_scores: dict[str, float] = {}

    def add_text(text: str, score: float) -> None:
        dates, times = _datetime_candidates(text)
        for value in dates:
            date_scores[value] = date_scores.get(value, 0.0) + score
        for value in times:
            time_scores[value] = time_scores.get(value, 0.0) + score

    def ocr_variants(crop: np.ndarray, modes: tuple[int, ...], base_score: float) -> None:
        if crop.size == 0:
            return
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        big = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        variants = [
            (big, base_score + 2.0),
            (cv2.threshold(big, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1], base_score),
        ]
        for image, variant_score in variants:
            for psm in modes:
                try:
                    text = pytesseract.image_to_string(
                        image,
                        config=(
                            f"--oem 3 --psm {psm} "
                            "-c tessedit_char_whitelist=0123456789/:"
                        ),
                        timeout=1.5,
                    )
                except Exception:
                    continue
                psm_bonus = 2.0 if psm in (8, 13) else 1.0
                add_text(text, variant_score + psm_bonus)

    # A combined crop is often read correctly in one pass. Separate crops are
    # fallback passes and improve robustness when the date or time is faint.
    ocr_variants(combined, (13, 8, 7), 6.0)
    if not date_scores:
        ocr_variants(date_crop, (8, 13, 7), 5.0)
    if not time_scores:
        ocr_variants(time_crop, (7, 8, 13), 5.0)

    if not date_scores or not time_scores:
        return None, "timestamp not confidently detected"

    date_value = max(date_scores.items(), key=lambda item: item[1])[0]
    time_value = max(time_scores.items(), key=lambda item: item[1])[0]
    return f"{date_value} {time_value}", "top-right header OCR"


# ------------------------- Template value recognizer ------------------------ #

TEMPLATE_VALUE_ROIS = {
    # Tight, value-only regions after perspective correction. These deliberately
    # avoid the label/drop-down row above and the button row below.
    "elong": (0.245, 0.145, 0.430, 0.240),
    "maxforce": (0.725, 0.145, 0.915, 0.240),
}


def _coerce_template_glyph(glyph: np.ndarray,
                           target_shape: tuple[int, int] = (72, 44)) -> Optional[np.ndarray]:
    """
    Convert any saved/trained glyph to the canonical template shape.

    Older user-trained template files may contain glyphs with slightly different
    pixel dimensions. NumPy cannot save those together with np.stack(), which
    caused the Teach recognizer command to fail with:
        "all input arrays must have the same shape"

    The recognizer only needs a normalized binary glyph, so resizing here is safe
    and keeps old template files usable.
    """
    if glyph is None:
        return None
    arr = np.asarray(glyph)
    if arr.size == 0:
        return None
    if arr.ndim == 3:
        arr = arr[..., 0]
    if arr.ndim != 2:
        return None
    arr = arr.astype(np.uint8)
    th, tw = target_shape
    if arr.shape != (th, tw):
        arr = cv2.resize(arr, (tw, th), interpolation=cv2.INTER_NEAREST)
    arr = (arr > 0).astype(np.uint8) * 255
    return arr


def _load_digit_template_arrays() -> dict[str, list[np.ndarray]]:
    """Load trained templates.

    The persistent Rahti training file configured by YDL_TEMPLATE_PATH is tried
    first. User-trained templates are then tried before the packaged templates
    and finally the embedded fallback. Loaded glyphs are normalized to one shape.
    """
    paths = []
    env_path = os.environ.get("YDL_TEMPLATE_PATH", "").strip()
    if env_path:
        paths.append(Path(env_path))
    try:
        script_dir = Path(__file__).resolve().parent
        paths.append(script_dir / "digit_templates_user.npz")
        paths.append(script_dir / "digit_templates.npz")
    except Exception:
        pass
    paths.append(Path.cwd() / "digit_templates_user.npz")
    paths.append(Path.cwd() / "digit_templates.npz")

    data = None
    for path in paths:
        if path.exists():
            try:
                data = np.load(str(path), allow_pickle=False)
                break
            except Exception:
                data = None

    if data is None:
        raw = base64.b64decode("".join(EMBEDDED_DIGIT_TEMPLATES_B64.split()))
        data = np.load(io.BytesIO(raw), allow_pickle=False)

    templates: dict[str, list[np.ndarray]] = {}
    for key in data.files:
        if not key.startswith("char_"):
            continue
        label = "." if key == "char_dot" else key.split("_", 1)[1]
        arr = data[key]
        glyphs: list[np.ndarray] = []
        if arr.ndim == 2:
            glyph = _coerce_template_glyph(arr)
            if glyph is not None:
                glyphs.append(glyph)
        elif arr.ndim >= 3:
            for g in arr:
                glyph = _coerce_template_glyph(g)
                if glyph is not None:
                    glyphs.append(glyph)
        if glyphs:
            templates[label] = glyphs
    for ch in list("0123456789."):
        templates.setdefault(ch, [])
    return templates


_DIGIT_TEMPLATES: Optional[dict[str, list[np.ndarray]]] = None


def get_digit_templates() -> dict[str, list[np.ndarray]]:
    global _DIGIT_TEMPLATES
    if _DIGIT_TEMPLATES is None:
        _DIGIT_TEMPLATES = _load_digit_template_arrays()
    return _DIGIT_TEMPLATES


def _clean_template_mask(mask: np.ndarray) -> np.ndarray:
    mask = cv2.medianBlur(mask, 3)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))

    h, w = mask.shape[:2]
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    clean = np.zeros_like(mask)
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if area < 10 or bh < 4:
            continue
        if bw > 0.85 * w or bh > 0.90 * h:
            continue
        # Remove long border lines at the bottom of the value box.
        if y > 0.78 * h and bh < 0.15 * h:
            continue
        if area > 0.35 * w * h and (bh < 0.25 * h or bw > 0.75 * w):
            continue
        clean[labels == i] = 255
    return clean


def template_candidate_masks(crop_bgr: np.ndarray, color: str) -> list[np.ndarray]:
    """Return several binary digit masks; the recognizer chooses the best one."""
    if crop_bgr.size == 0:
        return []
    hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    b, g, r = cv2.split(crop_bgr.astype(np.int16))
    masks: list[np.ndarray] = []

    if color == "green":
        masks.append(cv2.inRange(hsv, np.array([45, 70, 60]), np.array([90, 255, 255])))
        masks.append((((g - r) > 25) & ((g - b) > 15) & (g > 100)).astype(np.uint8) * 255)
        masks.append((((2 * g - r - b) > 55) & (g > 100)).astype(np.uint8) * 255)
        med = np.median(gray)
        masks.append((gray < med - 18).astype(np.uint8) * 255)

    elif color == "purple":
        score = ((r + b) // 2) - g
        masks.append(((score > 4) & (r > 70) & (b > 70)).astype(np.uint8) * 255)
        masks.append(cv2.inRange(hsv, np.array([105, 8, 50]), np.array([178, 255, 255])))
        # Useful when the purple digits appear grey or washed out.
        med = np.median(gray)
        masks.append((gray < med - 14).astype(np.uint8) * 255)
        masks.append((gray < med - 20).astype(np.uint8) * 255)

    elif color == "orange":
        masks.append(cv2.inRange(hsv, np.array([0, 30, 60]), np.array([40, 255, 255])))
        masks.append(((r - g > 5) & (r - b > 35) & (r > 90)).astype(np.uint8) * 255)
        masks.append(((r + g - 2 * b > 55) & (r > 85) & (g > 60)).astype(np.uint8) * 255)

    else:
        masks.append(cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1])

    cleaned = [_clean_template_mask(m) for m in masks]
    return [m for m in cleaned if cv2.countNonZero(m) > 20]


def segment_template_characters(mask: np.ndarray) -> list[tuple[int, int, str]]:
    """Segment a value-box mask into digit/dot x-intervals."""
    h, w = mask.shape[:2]
    col = (mask > 0).sum(axis=0)
    threshold = max(2, int(h * 0.02))
    active = col > threshold

    runs: list[list[int]] = []
    start = None
    for i, is_active in enumerate(active):
        if is_active and start is None:
            start = i
        if (not is_active or i == w - 1) and start is not None:
            end = i if not is_active else i + 1
            if end - start >= 2:
                runs.append([start, end])
            start = None

    infos = []
    for s, e in runs:
        sub = mask[:, s:e]
        ys, xs = np.nonzero(sub)
        if len(xs) == 0:
            continue
        y1, y2 = int(ys.min()), int(ys.max()) + 1
        infos.append((s, e, y1, y2, e - s, y2 - y1, len(xs)))

    if not infos:
        return []

    max_h = max(i[5] for i in infos)
    max_area = max(i[6] for i in infos)
    filtered = []
    for info in infos:
        s, e, y1, y2, bw, bh, area = info
        # A decimal point is short, narrow, and close to the digit baseline.
        if bh < 0.35 * max_h:
            if y1 > 0.45 * max_h and bw < 0.45 * max_h and area > 8:
                filtered.append(info)
        else:
            if area > 0.025 * max_area:
                filtered.append(info)

    if not filtered:
        return []

    max_h = max(i[5] for i in filtered)
    widths = [bw for _s, _e, _y1, _y2, bw, bh, _area in filtered
              if bh > 0.55 * max_h and bw > 0.25 * max_h]
    typical_width = float(np.median(widths) if widths else max_h * 0.60)
    typical_width = float(np.clip(typical_width, max_h * 0.45, max_h * 0.80))

    out: list[tuple[int, int, str]] = []
    for s, e, y1, y2, bw, bh, area in filtered:
        if bh < 0.35 * max_h or bw < 0.32 * typical_width:
            out.append((s, e, "dot"))
            continue

        n_parts = max(1, int(round(bw / typical_width)))
        if n_parts <= 1 or bw < 1.45 * typical_width:
            out.append((s, e, "digit"))
        else:
            # Split a connected pair such as "98" or "52" at the local valley
            # closest to the expected split position.
            prev = s
            for k in range(1, n_parts):
                target = s + bw * k / n_parts
                lo = int(max(prev + typical_width * 0.35, target - typical_width * 0.25))
                hi = int(min(e - typical_width * 0.35, target + typical_width * 0.25))
                if hi <= lo:
                    cut = int(round(target))
                else:
                    cut = lo + int(np.argmin(col[lo:hi]))
                out.append((prev, cut, "digit"))
                prev = cut
            out.append((prev, e, "digit"))

    return out


def normalize_template_glyph(mask: np.ndarray, interval: tuple[int, int, str],
                             size: tuple[int, int] = (44, 72)) -> Optional[np.ndarray]:
    s, e, _kind = interval
    sub = mask[:, s:e]
    ys, xs = np.nonzero(sub)
    if len(xs) == 0:
        return None
    glyph = sub[int(ys.min()):int(ys.max()) + 1, int(xs.min()):int(xs.max()) + 1]
    W, H = size
    gh, gw = glyph.shape[:2]
    scale = min((W - 6) / max(gw, 1), (H - 6) / max(gh, 1))
    nw = max(1, int(round(gw * scale)))
    nh = max(1, int(round(gh * scale)))
    small = cv2.resize(glyph, (nw, nh), interpolation=cv2.INTER_AREA)
    _, small = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    canvas = np.zeros((H, W), np.uint8)
    x = (W - nw) // 2
    y = (H - nh) // 2
    canvas[y:y + nh, x:x + nw] = small
    return canvas


def template_similarity(a: np.ndarray, b: np.ndarray) -> float:
    aa = a > 0
    bb = b > 0
    inter = np.logical_and(aa, bb).sum()
    denom = aa.sum() + bb.sum()
    return float(2.0 * inter / denom) if denom else 0.0


def classify_template_digit(glyph: np.ndarray) -> tuple[str, float]:
    templates = get_digit_templates()
    best_char = "?"
    best_score = -1.0
    for ch, arrs in templates.items():
        if ch == ".":
            continue
        for tmpl in arrs:
            score = template_similarity(glyph, tmpl)
            if score > best_score:
                best_score = score
                best_char = ch
    return best_char, best_score


def text_to_fixed_decimal(text: str, decimal_places: int = 2) -> tuple[Optional[float], str]:
    # The tester result boxes show two decimals. Even if the decimal dot is
    # faint or segmented out, the last two digits are decimals.
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) <= decimal_places:
        return None, text
    fixed = digits[:-decimal_places] + "." + digits[-decimal_places:]
    try:
        return float(fixed), fixed
    except ValueError:
        return None, fixed


def template_recognize_colored_number(crop_bgr: np.ndarray, color: str,
                                      expected_range: tuple[float, float],
                                      decimal_places: int = 2,
                                      expected_integer_digits: Optional[int] = None) -> tuple[Optional[float], str, str]:
    """Read a value box using template matching, not OCR."""
    best: Optional[tuple[float, float, str, str]] = None
    masks = template_candidate_masks(crop_bgr, color)

    for mask_index, mask in enumerate(masks):
        seg = segment_template_characters(mask)
        if not seg:
            continue

        chars = []
        scores = []
        for interval in seg:
            if interval[2] == "dot":
                chars.append(".")
                scores.append(0.75)
                continue
            glyph = normalize_template_glyph(mask, interval)
            if glyph is None:
                continue
            ch, score = classify_template_digit(glyph)
            chars.append(ch)
            scores.append(score)

        raw = "".join(chars)
        value, fixed = text_to_fixed_decimal(raw, decimal_places)
        if value is None:
            continue

        lo, hi = expected_range
        range_penalty = 0.0 if lo <= value <= hi else 60.0
        digits = "".join(ch for ch in raw if ch.isdigit())
        dot_penalty = 7.0 * abs(raw.count(".") - 1)
        len_penalty = 0.0
        if expected_integer_digits is not None:
            len_penalty = 3.0 * abs(len(digits) - (expected_integer_digits + decimal_places))

        score_value = float(np.mean(scores)) * 100.0 - dot_penalty - len_penalty - range_penalty
        note = f"template mask {mask_index}: raw={raw}, fixed={fixed}, score={score_value:.1f}"
        cand = (score_value, value, fixed, note)
        if best is None or cand[0] > best[0]:
            best = cand

    if best is None:
        return None, "", "template failed"

    _score, value, fixed, note = best
    return value, fixed, note


def train_templates_from_photos(image_label_rows: list[tuple[str, str, str, str, str]],
                                output_npz: str) -> None:
    """
    Utility function for retraining templates.

    Each row is: (image_path, force_text, elong_text, speed_text, maxforce_text).
    The photo is perspective-corrected first, then the fixed value regions are
    segmented and matched to the supplied label text.
    """
    field_specs = {
        "force": ((0.010, 0.145, 0.245, 0.240), "orange"),
        "elong": (TEMPLATE_VALUE_ROIS["elong"], "green"),
        "maxforce": (TEMPLATE_VALUE_ROIS["maxforce"], "purple"),
    }
    labels_by_field = ["force", "elong", "speed", "maxforce"]
    templates: dict[str, list[np.ndarray]] = {str(i): [] for i in range(10)}
    templates["."] = []

    for row in image_label_rows:
        image_path = row[0]
        text_map = dict(zip(labels_by_field, row[1:]))
        img = cv2.imread(image_path, cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError(f"Could not read {image_path}")
        rectified = perspective_rectify(img, detect_screen_corners(img))
        h, w = rectified.shape[:2]
        for field, (xyxy, color) in field_specs.items():
            text = text_map.get(field, "")
            if not text:
                continue
            roi = fixed_rect(w, h, xyxy)
            crop = rectified[roi.as_slice()]
            best_mask = None
            best_seg = None
            best_score = -1e9
            for mask in template_candidate_masks(crop, color):
                seg = segment_template_characters(mask)
                score = -20 * abs(len(seg) - len(text)) - 10 * abs(sum(1 for s in seg if s[2] == "dot") - text.count("."))
                if score > best_score:
                    best_score = score
                    best_mask = mask
                    best_seg = seg
            if best_mask is None or best_seg is None or len(best_seg) != len(text):
                raise RuntimeError(f"Could not segment {Path(image_path).name} {field}={text}; got {best_seg}")
            for ch, interval in zip(text, best_seg):
                glyph = normalize_template_glyph(best_mask, interval)
                if glyph is not None and ch in templates:
                    templates[ch].append(glyph)

    arrays = {}
    for ch, glyphs in templates.items():
        if glyphs:
            arrays["char_dot" if ch == "." else f"char_{ch}"] = np.stack(glyphs)
    np.savez_compressed(output_npz, **arrays)




def _normalise_label_text(text: str, decimal_places: int = 2) -> str:
    """Return a safe digit/dot label such as 1.98 or 52.49."""
    t = str(text).strip().replace(",", ".")
    t = "".join(ch for ch in t if ch.isdigit() or ch == ".")
    if t.count(".") > 1:
        first = t.find(".")
        t = t[:first + 1] + t[first + 1:].replace(".", "")
    if "." not in t:
        digits = "".join(ch for ch in t if ch.isdigit())
        if len(digits) > decimal_places:
            t = digits[:-decimal_places] + "." + digits[-decimal_places:]
    try:
        v = float(t)
        t = f"{v:.{decimal_places}f}"
    except Exception:
        pass
    return t


def _template_output_path() -> Path:
    """Best writable location for user-trained digit templates."""
    env_path = os.environ.get("YDL_TEMPLATE_PATH", "").strip()
    if env_path:
        p = Path(env_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    candidates = []
    try:
        candidates.append(Path(__file__).resolve().parent / "digit_templates_user.npz")
    except Exception:
        pass
    candidates.append(Path.cwd() / "digit_templates_user.npz")
    for p in candidates:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            test = p.parent / ".write_test_digit_templates.tmp"
            test.write_text("x", encoding="utf-8")
            test.unlink(missing_ok=True)
            return p
        except Exception:
            continue
    return Path("digit_templates_user.npz")


def _save_templates_npz(templates: dict[str, list[np.ndarray]], path: str | Path) -> None:
    arrays = {}
    for ch, glyphs in templates.items():
        if not glyphs:
            continue
        good = []
        for g in glyphs:
            glyph = _coerce_template_glyph(g)
            if glyph is not None:
                good.append(glyph)
        if good:
            arrays["char_dot" if ch == "." else f"char_{ch}"] = np.stack(good, axis=0)
    if not arrays:
        raise RuntimeError("No template glyphs to save.")
    np.savez_compressed(str(path), **arrays)


def _best_mask_and_segments_for_label(crop_bgr: np.ndarray, color: str, label_text: str):
    label = _normalise_label_text(label_text)
    digit_count = sum(ch.isdigit() for ch in label)
    dot_count = label.count(".")
    best = None
    for mask in template_candidate_masks(crop_bgr, color):
        seg = segment_template_characters(mask)
        if not seg:
            continue
        seg_digit_count = sum(1 for s in seg if s[2] != "dot")
        seg_dot_count = sum(1 for s in seg if s[2] == "dot")
        score = 100
        score -= 35 * abs(seg_digit_count - digit_count)
        score -= 20 * abs(seg_dot_count - dot_count)
        score -= 8 * abs(len(seg) - len(label))
        # Prefer masks that give reasonably sized glyphs but not huge border artifacts.
        widths = [max(1, s[1] - s[0]) for s in seg if s[2] != "dot"]
        if widths:
            score += min(10, float(np.median(widths)))
        if best is None or score > best[0]:
            best = (score, mask, seg)
    if best is None:
        return None, []
    return best[1], best[2]


def add_templates_from_corrected_values(rectified_bgr: np.ndarray,
                                        elong_text: str,
                                        maxforce_text: str,
                                        output_npz: Optional[str | Path] = None) -> tuple[Path, dict[str, int]]:
    """Add templates from the current corrected screen and user-entered values.\n\n    The screen has already been perspective-corrected.  The function extracts\n    glyphs from the fixed Elong. and Maximum force value boxes and appends them to\n    the loaded template set.  This improves future recognitions without relying\n    on Tesseract OCR.\n    """
    if rectified_bgr is None or rectified_bgr.size == 0:
        raise RuntimeError("No corrected screen image is available.")
    h, w = rectified_bgr.shape[:2]
    fields = [
        ("elong", TEMPLATE_VALUE_ROIS["elong"], "green", _normalise_label_text(elong_text)),
        ("maxforce", TEMPLATE_VALUE_ROIS["maxforce"], "purple", _normalise_label_text(maxforce_text)),
    ]
    templates = get_digit_templates()
    # Deep-copy the list containers so we do not partially alter the global set on failure.
    new_templates = {ch: [g.copy() for g in glyphs] for ch, glyphs in templates.items()}
    for ch in list("0123456789."):
        new_templates.setdefault(ch, [])
    added = {ch: 0 for ch in list("0123456789.")}

    for field, xyxy, color, label in fields:
        if not label:
            continue
        roi = fixed_rect(w, h, xyxy)
        crop = rectified_bgr[roi.as_slice()]
        mask, seg = _best_mask_and_segments_for_label(crop, color, label)
        if mask is None or not seg:
            raise RuntimeError(f"Could not segment {field} value box for label {label!r}.")

        # Normal case: segmentation includes the decimal point.
        label_chars = list(label)
        intervals = list(seg)
        pairs = []
        if len(intervals) == len(label_chars):
            pairs = list(zip(label_chars, intervals))
        else:
            # Fallback: learn only digits if the decimal point was too faint to segment.
            digit_intervals = [s for s in intervals if s[2] != "dot"]
            digit_labels = [ch for ch in label_chars if ch.isdigit()]
            if len(digit_intervals) != len(digit_labels):
                raise RuntimeError(
                    f"Could not align {field} label {label!r}: {len(digit_intervals)} digit segments found."
                )
            pairs = list(zip(digit_labels, digit_intervals))

        for ch, interval in pairs:
            if ch == "." and interval[2] != "dot":
                continue
            if ch.isdigit() and interval[2] == "dot":
                continue
            glyph = normalize_template_glyph(mask, interval)
            glyph = _coerce_template_glyph(glyph)
            if glyph is not None and ch in new_templates:
                new_templates[ch].append(glyph)
                added[ch] = added.get(ch, 0) + 1

    total_added = sum(added.values())
    if total_added == 0:
        raise RuntimeError("No new glyph templates were added.")
    out = Path(output_npz) if output_npz else _template_output_path()
    _save_templates_npz(new_templates, out)
    global _DIGIT_TEMPLATES
    _DIGIT_TEMPLATES = new_templates
    return out, added

# ----------------------- Result box and graph detection -------------------- #

def fixed_rect(w: int, h: int, xyxy: tuple[float, float, float, float]) -> Rect:
    x1, y1, x2, y2 = xyxy
    return Rect(int(round(x1*w)), int(round(y1*h)),
                int(round(x2*w)), int(round(y2*h))).clip(w, h)


def find_top_result_boxes(rectified_bgr: np.ndarray) -> list[Rect]:
    """
    The tester UI layout is fixed after perspective correction. These normalized
    coordinates mark the value boxes and are not affected by glare.
    """
    h, w = rectified_bgr.shape[:2]
    return [
        fixed_rect(w, h, (0.018, 0.145, 0.246, 0.265)),  # Force
        fixed_rect(w, h, (0.250, 0.145, 0.486, 0.265)),  # Elong.
        fixed_rect(w, h, (0.500, 0.145, 0.737, 0.265)),  # Speed
        fixed_rect(w, h, (0.708, 0.135, 0.980, 0.265)),  # Maximum force, wide for glare/leading digit
    ]


def result_number_rois(rectified_bgr: np.ndarray) -> tuple[Rect, Rect]:
    """Tight, fixed number-only regions for Elong. and Maximum force."""
    h, w = rectified_bgr.shape[:2]
    elong_roi = fixed_rect(w, h, TEMPLATE_VALUE_ROIS["elong"])
    max_roi = fixed_rect(w, h, TEMPLATE_VALUE_ROIS["maxforce"])
    return elong_roi, max_roi


def _profile_peaks(profile: np.ndarray, threshold_fraction: float = 0.45, min_abs: float = 8.0) -> list[int]:
    """Return center positions of broad profile peaks, one per line."""
    profile = np.asarray(profile, dtype=float)
    if profile.size == 0 or float(np.nanmax(profile)) <= 0:
        return []
    thr = max(float(np.nanmax(profile)) * threshold_fraction, min_abs)
    peaks: list[int] = []
    in_run = False
    start = 0
    for i, v in enumerate(profile):
        active = bool(v >= thr)
        if active and not in_run:
            start = i
            in_run = True
        if in_run and ((not active) or i == len(profile) - 1):
            end = i - 1 if not active else i
            if end >= start:
                seg = profile[start:end + 1]
                peaks.append(start + int(np.argmax(seg)))
            in_run = False
    # Merge near-duplicates from thick lines or antialiasing.
    merged: list[int] = []
    for p in peaks:
        if not merged or p - merged[-1] > 4:
            merged.append(p)
        else:
            merged[-1] = int(round((merged[-1] + p) / 2))
    return merged


def _median_grid_spacing(peaks: list[int], minimum: float) -> Optional[float]:
    if len(peaks) < 3:
        return None
    diffs = np.diff(np.asarray(peaks, dtype=float))
    diffs = diffs[diffs >= minimum]
    if len(diffs) < 2:
        return None
    return float(np.median(diffs))


def refine_plot_to_grid_axes(rectified_bgr: np.ndarray, rough: Rect) -> Rect:
    """Refine the graph rectangle to the actual axis grid lines.

    The dark graph has a top frame above the first y-axis gridline. The red
    labels are placed at gridline positions, so the data mapping must use the
    topmost labelled gridline, not the outer black frame. This function finds
    the cyan/blue gridline peaks and moves the plot rectangle onto the actual
    axis grid.
    """
    h, w = rectified_bgr.shape[:2]
    rough = rough.clip(w, h)
    roi = rectified_bgr[rough.as_slice()]
    if roi.size == 0:
        return rough
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    # Cyan/blue gridlines in the black plot area. The mask deliberately avoids
    # the green curve and red axis labels.
    mask = cv2.inRange(hsv, np.array([75, 12, 65]), np.array([135, 255, 255]))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)), iterations=1)
    row_peaks = _profile_peaks(mask.sum(axis=1), 0.45, max(10, 0.20 * roi.shape[1]))
    col_peaks = _profile_peaks(mask.sum(axis=0), 0.45, max(10, 0.20 * roi.shape[0]))

    y1, y2 = 0, roi.shape[0] - 1
    row_spacing = _median_grid_spacing(row_peaks, max(12, 0.035 * roi.shape[0]))
    if row_spacing and len(row_peaks) >= 4:
        # If there is a top frame/border before the first labelled gridline,
        # the first gap is much shorter than the regular grid spacing. Skip it.
        first = row_peaks[0]
        if len(row_peaks) >= 2 and (row_peaks[1] - row_peaks[0]) < 0.70 * row_spacing:
            first = row_peaks[1]
        last = row_peaks[-1]
        # Y axis is normally 0..120 N, i.e. 12 intervals. Prefer a 12-interval
        # span when that pattern is present.
        best_pair = (first, last)
        best_score = abs(((last - first) / row_spacing) - round((last - first) / row_spacing))
        for a in row_peaks[:3]:
            for b in row_peaks[-3:]:
                if b <= a:
                    continue
                intervals = (b - a) / row_spacing
                score = abs(intervals - 12.0) + 0.03 * abs(round(intervals) - intervals)
                if score < best_score:
                    best_pair = (a, b)
                    best_score = score
        y1, y2 = best_pair

    x1, x2 = 0, roi.shape[1] - 1
    col_spacing = _median_grid_spacing(col_peaks, max(12, 0.020 * roi.shape[1]))
    if col_spacing and len(col_peaks) >= 5:
        first = col_peaks[0]
        # Estimate the rightmost axis line even when the last line is hidden by
        # the edge or is not picked up by the color threshold. For the common
        # 0..5 mm display, the grid has 25 small intervals.
        n_intervals = int(round((roi.shape[1] - 1 - first) / col_spacing))
        n_intervals = max(n_intervals, len(col_peaks) - 1)
        estimated_last = int(round(first + n_intervals * col_spacing))
        if estimated_last > roi.shape[1] - 1 and estimated_last - (roi.shape[1] - 1) <= 0.25 * col_spacing:
            estimated_last = roi.shape[1] - 1
        if 0 < estimated_last < roi.shape[1] + 0.35 * col_spacing:
            x1, x2 = first, min(roi.shape[1] - 1, estimated_last)
        else:
            x1, x2 = first, col_peaks[-1]

    refined = Rect(rough.x1 + int(x1), rough.y1 + int(y1),
                   rough.x1 + int(x2), rough.y1 + int(y2)).clip(w, h)
    # Sanity check: do not allow a tiny or wildly shifted plot.
    if refined.width < 0.45 * w or refined.height < 0.30 * h:
        return rough
    return refined


def find_graph_plot(rectified_bgr: np.ndarray) -> Rect:
    """
    Return the plotting rectangle of the YDL-7003-P Force/Elong. graph.

    The returned rectangle is aligned to the actual axis gridlines: y_max is on
    the top labelled gridline and y_min on the bottom gridline. This avoids the
    earlier scaling error caused by using the black frame above the top gridline.
    """
    h, w = rectified_bgr.shape[:2]
    r = Rect(int(round(0.070*w)), int(round(0.415*h)),
             int(round(0.700*w)), int(round(0.910*h))).clip(w, h)

    # Small refinement: find the actual dark plot border near the fixed ROI.
    pad_x = int(0.025*w)
    pad_y = int(0.035*h)
    search = Rect(r.x1-pad_x, r.y1-pad_y, r.x2+pad_x, r.y2+pad_y).clip(w, h)
    crop = rectified_bgr[search.as_slice()]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    mask = cv2.inRange(gray, 0, 95)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9)), iterations=1)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        rr = Rect(search.x1+x, search.y1+y, search.x1+x+bw, search.y1+y+bh)
        if bw > 0.45*w and bh > 0.35*h:
            cx = (rr.x1+rr.x2)/2; cy = (rr.y1+rr.y2)/2
            target_cx = (r.x1+r.x2)/2; target_cy = (r.y1+r.y2)/2
            dist = abs(cx-target_cx)/w + abs(cy-target_cy)/h
            area = bw*bh
            score = area - 2_000_000*dist
            if best is None or score > best[0]:
                best = (score, rr)
    if best is not None:
        rr = best[1]
        if (0.045*w <= rr.x1 <= 0.10*w and 0.64*w <= rr.x2 <= 0.73*w and
                0.38*h <= rr.y1 <= 0.46*h and 0.86*h <= rr.y2 <= 0.94*h):
            r = rr.clip(w, h)
    return refine_plot_to_grid_axes(rectified_bgr, r)



def graph_corners_from_rect(rect: Rect) -> np.ndarray:
    """Return graph corners as TL, TR, BR, BL floating-point points."""
    return rect_to_corners(rect).astype(np.float32)


def graph_corners_to_rect(corners: np.ndarray, width: int, height: int) -> Rect:
    """Return the bounding rectangle of a graph quadrilateral."""
    q = order_quad(np.asarray(corners, dtype=np.float32).reshape(4, 2))
    x1 = int(np.floor(np.min(q[:, 0])))
    y1 = int(np.floor(np.min(q[:, 1])))
    x2 = int(np.ceil(np.max(q[:, 0]))) + 1
    y2 = int(np.ceil(np.max(q[:, 1]))) + 1
    return Rect(x1, y1, x2, y2).clip(width, height)


def warp_graph_quad(rectified_bgr: np.ndarray, corners: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Perspective-correct an individually adjustable graph quadrilateral."""
    q = order_quad(np.asarray(corners, dtype=np.float32).reshape(4, 2))
    top = float(np.linalg.norm(q[1] - q[0]))
    bottom = float(np.linalg.norm(q[2] - q[3]))
    left = float(np.linalg.norm(q[3] - q[0]))
    right = float(np.linalg.norm(q[2] - q[1]))
    out_w = max(120, int(round(max(top, bottom))))
    out_h = max(100, int(round(max(left, right))))
    dst = np.array(
        [[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]],
        dtype=np.float32,
    )
    to_warp = cv2.getPerspectiveTransform(q, dst)
    to_screen = cv2.getPerspectiveTransform(dst, q)
    warped = cv2.warpPerspective(
        rectified_bgr,
        to_warp,
        (out_w, out_h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return warped, to_screen


def extract_green_curve_quad(rectified_bgr: np.ndarray, corners: np.ndarray,
                             x_min: float, x_max: float,
                             y_min: float, y_max: float) -> np.ndarray:
    """Digitize the curve from a four-corner graph area."""
    warped, _ = warp_graph_quad(rectified_bgr, corners)
    h, w = warped.shape[:2]
    return extract_green_curve(warped, Rect(0, 0, w, h), x_min, x_max, y_min, y_max)


def validate_expected_layout(rectified_bgr: np.ndarray,
                             screen_detection_ok: bool = True) -> dict:
    """Check that an uploaded image resembles the Force/Elong. result screen."""
    h, w = rectified_bgr.shape[:2]
    issues: list[str] = []
    checks: dict[str, dict] = {}

    gr = fixed_rect(w, h, (0.050, 0.350, 0.720, 0.950))
    graph = rectified_bgr[gr.as_slice()]
    gray = cv2.cvtColor(graph, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(graph, cv2.COLOR_BGR2HSV)
    dark_fraction = float(np.mean(gray < 100))
    green = cv2.inRange(hsv, np.array([35, 75, 55]), np.array([95, 255, 255]))
    green_fraction = float(np.mean(green > 0))
    graph_ok = dark_fraction >= 0.28
    curve_ok = green_fraction >= 0.00045
    checks["graph_area"] = {"ok": bool(graph_ok), "dark_fraction": round(dark_fraction, 4)}
    checks["green_curve"] = {"ok": bool(curve_ok), "green_fraction": round(green_fraction, 6)}
    if not graph_ok:
        issues.append(
            "The expected dark Force-versus-extension graph is not visible in the lower-left area. "
            "The photograph may show a settings or method screen instead of a completed test result."
        )
    elif not curve_ok:
        issues.append("The graph area is present, but a green force/extension curve was not detected.")

    elong_roi, max_roi = result_number_rois(rectified_bgr)
    elong_masks = template_candidate_masks(rectified_bgr[elong_roi.as_slice()], "green")
    max_masks = template_candidate_masks(rectified_bgr[max_roi.as_slice()], "purple")
    elong_pixels = max((cv2.countNonZero(m) for m in elong_masks), default=0)
    max_pixels = max((cv2.countNonZero(m) for m in max_masks), default=0)
    elong_ok = elong_pixels >= max(80, int(elong_roi.width * elong_roi.height * 0.006))
    max_ok = max_pixels >= max(80, int(max_roi.width * max_roi.height * 0.004))
    checks["elongation_field"] = {"ok": bool(elong_ok), "colored_pixels": int(elong_pixels)}
    checks["maxforce_field"] = {"ok": bool(max_ok), "colored_pixels": int(max_pixels)}
    if not elong_ok:
        issues.append("The green Elongation value was not found in the second result box from the left.")
    if not max_ok:
        issues.append("The purple MaxForce value was not found in the result box on the right.")
    if not screen_detection_ok:
        issues.insert(0, "The tester display could not be detected reliably. Adjust the four screen corners manually.")

    required = [screen_detection_ok, graph_ok, curve_ok, elong_ok, max_ok]
    score = float(sum(bool(v) for v in required) / len(required))
    return {
        "compliant": bool(all(required)),
        "score": round(score, 2),
        "issues": issues,
        "checks": checks,
    }


def tesseract_tokens(image_bgr: np.ndarray, psm: int = 6):
    if pytesseract is None:
        return []
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
    cfg = f"--oem 3 --psm {psm} -c tessedit_char_whitelist=0123456789.,-"
    try:
        d = pytesseract.image_to_data(gray, config=cfg, output_type=Output.DICT)
    except Exception:
        return []

    out = []
    for i, txt in enumerate(d["text"]):
        val = parse_number(txt)
        if val is None:
            continue
        try:
            conf = float(d["conf"][i])
        except Exception:
            conf = -1
        x = (d["left"][i] + d["width"][i] / 2) / 3
        y = (d["top"][i] + d["height"][i] / 2) / 3
        out.append((x, y, val, conf, txt))
    return out


def estimate_axis_limits(rectified_bgr: np.ndarray, plot: Rect) -> tuple[float,float,float,float]:
    """
    OCR tick labels and infer min/max.

    The YDL screen normally uses zero origins and major labels at integers on X
    and multiples of 10 on Y. When OCR is incomplete, the highest recognized
    tick is extrapolated to the plot edge. Defaults are x=0..5 mm, y=0..120 N.
    """
    h, w = rectified_bgr.shape[:2]
    x_min, x_max, y_min, y_max = 0.0, 5.0, 0.0, 120.0

    # X labels: strip immediately below plot.
    xb = Rect(plot.x1, plot.y2, min(w, plot.x2), min(h, plot.y2 + int(.075*h))).clip(w,h)
    xt = tesseract_tokens(rectified_bgr[xb.as_slice()], psm=6)
    xvals = [(xb.x1+x, val) for x, _, val, conf, _ in xt if conf >= 0 and 0 <= val <= 100]
    if len(xvals) >= 2:
        px = np.array([p for p,v in xvals], float)
        vv = np.array([v for p,v in xvals], float)
        try:
            a, b = np.polyfit(px, vv, 1)
            if a > 0:
                x_min = max(0.0, a*plot.x1+b)
                x_max = a*plot.x2+b
        except Exception:
            pass
    elif xvals:
        p, v = max(xvals, key=lambda z: z[1])
        if v > 0 and p > plot.x1:
            x_max = v * (plot.x2-plot.x1) / (p-plot.x1)

    # Y labels: strip left of plot.
    yb = Rect(max(0, plot.x1-int(.075*w)), plot.y1, plot.x1, plot.y2).clip(w,h)
    yt = tesseract_tokens(rectified_bgr[yb.as_slice()], psm=6)
    # Y-axis labels on this instrument are zero or multiples of 10. Reject
    # isolated low OCR artefacts such as "4", which otherwise can turn a
    # 0..120 N axis into an implausible 0..12 N axis.
    yvals = [
        (yb.y1+y, val)
        for _, y, val, conf, _ in yt
        if conf >= 0 and 0 <= val <= 10000
        and (abs(val) < 1e-9 or (val >= 10 and abs(val/10.0 - round(val/10.0)) <= 0.16))
    ]
    if len(yvals) >= 2:
        py = np.array([p for p,v in yvals], float)
        vv = np.array([v for p,v in yvals], float)
        try:
            a, b = np.polyfit(py, vv, 1)
            if a < 0:
                y_max = a*plot.y1+b
                y_min = max(0.0, a*plot.y2+b)
        except Exception:
            pass
    elif yvals:
        p, v = max(yvals, key=lambda z: z[1])
        if v > 0 and plot.y2 > p:
            y_max = v * (plot.y2-plot.y1) / (plot.y2-p)

    # Snap near common display scales to suppress small OCR/geometric errors.
    def snap(value, choices, tolerance=.18):
        best = min(choices, key=lambda c: abs(c-value))
        return float(best) if abs(best-value) <= tolerance*max(best,1) else float(value)

    x_min = 0.0 if abs(x_min) < .5 else x_min
    y_min = 0.0 if abs(y_min) < 5 else y_min
    x_max = snap(x_max, [1,2,3,4,5,6,8,10,20,50])
    y_max = snap(y_max, [10,20,30,40,50,60,80,100,120,150,200,500,1000])
    return x_min, x_max, y_min, y_max


def extract_green_curve(rectified_bgr: np.ndarray, plot: Rect,
                        x_min: float, x_max: float,
                        y_min: float, y_max: float) -> np.ndarray:
    roi = rectified_bgr[plot.as_slice()]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

    # Bright lime-green trace. Saturation threshold rejects pale grid lines.
    mask = cv2.inRange(hsv, np.array([32, 95, 70]), np.array([92, 255, 255]))
    mask = cv2.morphologyEx(
        mask, cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3,3))
    )
    mask = cv2.morphologyEx(
        mask, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5,5))
    )

    ys, xs = np.nonzero(mask)
    if len(xs) < 20:
        return np.empty((0,2), dtype=float)

    # Remove small disconnected green objects outside the main trace.
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    keep = np.zeros_like(mask)
    components = []
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        bw = stats[i, cv2.CC_STAT_WIDTH]
        if area >= 15 and bw >= 5:
            components.append((area*bw, i))
    if components:
        # Keep all substantial components because a reflection can split the curve.
        threshold = max(20, max(s for s,i in components)*0.01)
        for score, i in components:
            if score >= threshold:
                keep[labels == i] = 255
        mask = keep

    points = []
    for x in range(mask.shape[1]):
        yy = np.flatnonzero(mask[:, x])
        if yy.size:
            # Median follows the center of a thick trace.
            points.append((x, float(np.median(yy))))

    if len(points) < 10:
        return np.empty((0,2), dtype=float)

    arr = np.asarray(points, float)
    px = arr[:,0]
    py = arr[:,1]

    # Small median smooth without erasing the near-vertical rupture segment.
    if len(py) >= 7:
        smooth = py.copy()
        for i in range(3, len(py)-3):
            smooth[i] = np.median(py[i-3:i+4])
        py = smooth

    xv = x_min + px / max(plot.width-1,1) * (x_max-x_min)
    yv = y_max - py / max(plot.height-1,1) * (y_max-y_min)
    return np.column_stack([xv, yv])


def curve_break_estimates(curve: Optional[np.ndarray]) -> tuple[Optional[float], Optional[float]]:
    """
    Rough independent estimates from the digitized graph:
    break elongation = last extracted x value; max force = maximum y value.
    Used only as a sanity check/fallback for OCR.
    """
    if curve is None or len(curve) < 5:
        return None, None
    return float(curve[-1, 0]), float(np.nanmax(curve[:, 1]))



def _median_smooth_1d(y: np.ndarray, window: int = 5) -> np.ndarray:
    y = np.asarray(y, dtype=float)
    if len(y) < 3 or window <= 1:
        return y.copy()
    window = int(window) | 1
    half = window // 2
    padded = np.pad(y, (half, half), mode="edge")
    return np.array([np.median(padded[i:i+window]) for i in range(len(y))], dtype=float)


def prepare_curve_for_mechanics(curve: Optional[np.ndarray]) -> np.ndarray:
    """Sort, de-duplicate, remove NaNs, and lightly smooth the digitized curve."""
    if curve is None or len(curve) < 3:
        return np.empty((0, 2), dtype=float)
    arr = np.asarray(curve, dtype=float)
    arr = arr[np.isfinite(arr[:, 0]) & np.isfinite(arr[:, 1])]
    if len(arr) < 3:
        return np.empty((0, 2), dtype=float)
    arr = arr[np.argsort(arr[:, 0])]
    x = arr[:, 0]
    y = np.maximum(arr[:, 1], 0.0)
    if len(x) > 1:
        rounded = np.round(x, 5)
        ux = []
        uy = []
        for val in np.unique(rounded):
            m = rounded == val
            ux.append(float(np.median(x[m])))
            uy.append(float(np.median(y[m])))
        arr = np.column_stack([ux, uy])
    arr[:, 1] = np.maximum(arr[:, 1], 0.0)
    return arr


def detect_break_index_from_force_drop(x: np.ndarray, y: np.ndarray,
                                       text_break_x: Optional[float],
                                       peak_force: float) -> tuple[int, str]:
    """Detect rupture from a sustained abrupt force drop.

    Returns the index immediately before the drop. If no sustained drop is
    found, falls back to the last point above a small force threshold.
    """
    n = len(x)
    if n < 5 or not np.isfinite(peak_force) or peak_force <= 0:
        return max(0, n - 1), "break-extension fallback: last point"
    peak_idx = int(np.nanargmax(y))
    window = max(3, min(12, n // 35))
    min_drop = max(3.0, 0.12 * peak_force)
    start = max(1, peak_idx)
    candidates: list[tuple[int, float, float]] = []
    for i in range(start, max(start, n - window - 1)):
        if y[i] < 0.45 * peak_force:
            continue
        future = y[i + 1:i + 1 + window]
        if len(future) < 2:
            continue
        drop = float(y[i] - np.nanmin(future))
        if drop >= min_drop:
            # Require the drop to persist for at least half the look-ahead window.
            if np.count_nonzero(future <= y[i] - 0.65 * min_drop) >= max(1, window // 2):
                score = drop / peak_force
                if text_break_x is not None and text_break_x > 0:
                    score -= 0.35 * abs(float(x[i]) - text_break_x) / max(text_break_x, 1e-9)
                candidates.append((i, score, drop))
    if candidates:
        # Prefer a candidate near the text-box elongation if available; otherwise
        # use the strongest sustained drop.
        if text_break_x is not None and text_break_x > 0:
            close = [c for c in candidates if abs(float(x[c[0]]) - text_break_x) <= max(0.25, 0.20 * text_break_x)]
            if close:
                i, _score, drop = max(close, key=lambda c: c[1])
                return int(i), f"break extension: sustained force drop ({drop:.2g} N), constrained near text-box value"
        i, _score, drop = max(candidates, key=lambda c: c[1])
        return int(i), f"break extension: sustained force drop ({drop:.2g} N)"

    # Derivative fallback: a large negative slope after peak.
    dx = np.diff(x)
    dy = np.diff(y)
    valid = dx > max(1e-6, 0.002 * max(float(x[-1] - x[0]), 1e-9))
    if np.any(valid):
        deriv = np.full_like(dy, np.nan, dtype=float)
        deriv[valid] = dy[valid] / dx[valid]
        search = np.arange(max(peak_idx, 1), n - 1)
        if len(search):
            j = int(search[np.nanargmin(deriv[search])])
            if np.isfinite(deriv[j]) and dy[j] <= -max(2.0, 0.07 * peak_force):
                return max(0, j), "break extension: steepest negative force derivative"

    threshold = max(2.0, 0.08 * peak_force)
    valid_idx = np.flatnonzero(y >= threshold)
    if len(valid_idx):
        return int(valid_idx[-1]), "break-extension fallback: last point above force threshold"
    return n - 1, "break-extension fallback: last extracted point"


def calculate_mechanical_properties(result: AnalysisResult,
                                    gauge_length_mm: float = 50.0,
                                    sample_width_mm: float = 15.0,
                                    thickness_um: Optional[float] = None,
                                    grammage_g_m2: Optional[float] = 100.0) -> None:
    """
    Calculate robust mechanical-test values from the digitized curve.

    The curve gives Force [N] vs Elongation [mm]. The initial fitted slope is
    N/mm. With gauge length and sample width, slope is converted to tensile
    stiffness in kN/m as slope * gauge_length / width. If thickness is supplied,
    a true Young's modulus in MPa is also calculated as
    slope * gauge_length / (width * thickness).
    """
    manual_break_extension = result.manual_break_extension
    result.break_is_manual = False
    result.elongation_data = None
    result.max_force_data = None
    result.elongation_text_percent = None
    result.elongation_data_percent = None
    result.elastic_slope_n_per_mm = None
    result.tensile_stiffness_kn_per_m = None
    result.tensile_stiffness_index_knm_per_kg = None
    result.elastic_modulus_mpa = None
    result.modulus_r2 = None
    result.modulus_line = None
    result.break_line_x = None
    result.toughness_n_mm = None
    result.toughness_mj = None
    result.mechanical_note = ""

    curve = prepare_curve_for_mechanics(result.curve_xy)
    if len(curve) < 8:
        result.mechanical_note = "Too few curve points for mechanical calculations."
        return

    x = curve[:, 0].astype(float)
    y_raw = curve[:, 1].astype(float)
    y = _median_smooth_1d(y_raw, 5)
    peak_force = float(np.nanmax(y))
    if not np.isfinite(peak_force) or peak_force <= 0:
        result.mechanical_note = "No positive force values found."
        return

    result.max_force_data = float(np.nanmax(y_raw))
    auto_break_idx, break_note = detect_break_index_from_force_drop(
        x, y, result.elongation, peak_force
    )

    use_manual_break = (
        manual_break_extension is not None
        and np.isfinite(manual_break_extension)
        and float(x[0]) <= float(manual_break_extension) <= float(x[-1])
    )
    if use_manual_break:
        break_idx = int(np.nanargmin(np.abs(x - float(manual_break_extension))))
        result.elongation_data = float(x[break_idx])
        result.manual_break_extension = result.elongation_data
        result.break_is_manual = True
        result.mechanical_note = "break extension manually selected"
    else:
        break_idx = auto_break_idx
        result.elongation_data = float(x[break_idx])
        result.break_is_manual = False
        result.mechanical_note = break_note
    result.break_line_x = result.elongation_data

    if gauge_length_mm and gauge_length_mm > 0:
        if result.elongation is not None:
            result.elongation_text_percent = 100.0 * result.elongation / gauge_length_mm
        if result.elongation_data is not None:
            result.elongation_data_percent = 100.0 * result.elongation_data / gauge_length_mm

    end_mask = x <= result.elongation_data + 1e-9
    xi = x[end_mask]
    yi = np.maximum(y_raw[end_mask], 0.0)
    if len(xi) >= 2:
        if xi[0] > 1e-6:
            xi = np.insert(xi, 0, 0.0)
            yi = np.insert(yi, 0, 0.0)
        result.toughness_n_mm = float(trapezoid_integral(yi, xi))
        result.toughness_mj = result.toughness_n_mm  # 1 N·mm = 1 mJ

    x_break = max(float(result.elongation_data or x[-1]), 1e-9)
    candidate = np.flatnonzero(
        (x <= 0.70 * x_break) &
        (y >= 0.08 * peak_force) &
        (y <= 0.60 * peak_force)
    )
    if len(candidate) < 8:
        candidate = np.flatnonzero(
            (x <= 0.80 * x_break) &
            (y >= 0.04 * peak_force) &
            (y <= 0.70 * peak_force)
        )

    best = None
    if len(candidate) >= 8:
        min_pts = max(8, min(30, len(candidate) // 4 if len(candidate) >= 32 else 8))
        possible_lengths = sorted(set([min_pts, min_pts * 2, min_pts * 3, min(len(candidate), max(min_pts, 45))]))
        step = max(1, min_pts // 3)
        for npts in possible_lengths:
            if npts > len(candidate):
                continue
            for start in range(0, len(candidate) - npts + 1, step):
                idx = candidate[start:start+npts]
                xx = x[idx]
                yy = y[idx]
                if xx[-1] - xx[0] < max(0.025 * x_break, 0.015):
                    continue
                try:
                    m, b = np.polyfit(xx, yy, 1)
                except Exception:
                    continue
                if not np.isfinite(m) or m <= 0:
                    continue
                pred = m * xx + b
                ss_res = float(np.sum((yy - pred) ** 2))
                ss_tot = float(np.sum((yy - np.mean(yy)) ** 2))
                r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else 0.0
                intercept_penalty = min(0.5, abs(b) / max(peak_force, 1e-9))
                late_penalty = 0.08 * float(np.mean(xx) / x_break)
                width_bonus = min(0.08, 0.20 * float((xx[-1] - xx[0]) / x_break))
                score = r2 + width_bonus - 0.18 * intercept_penalty - late_penalty
                if best is None or score > best[0]:
                    best = (score, float(m), float(b), float(r2), int(idx[0]), int(idx[-1]))

    if best is not None:
        _score, slope, intercept, r2, i1, i2 = best
        result.elastic_slope_n_per_mm = slope
        result.modulus_r2 = r2
        x1 = float(x[i1])
        x2 = float(x[i2])
        y1 = float(slope * x1 + intercept)
        y2 = float(slope * x2 + intercept)
        result.modulus_line = (x1, y1, x2, y2)
        if gauge_length_mm > 0 and sample_width_mm > 0:
            result.tensile_stiffness_kn_per_m = slope * gauge_length_mm / sample_width_mm
            if grammage_g_m2 is not None and grammage_g_m2 > 0:
                result.tensile_stiffness_index_knm_per_kg = (
                    result.tensile_stiffness_kn_per_m / (grammage_g_m2 / 1000.0)
                )
            if thickness_um is not None and thickness_um > 0:
                thickness_mm = thickness_um / 1000.0
                result.elastic_modulus_mpa = slope * gauge_length_mm / (sample_width_mm * thickness_mm)
    else:
        extra = "No sufficiently linear early segment found for tensile modulus fit."
        result.mechanical_note = (result.mechanical_note + "; " + extra) if result.mechanical_note else extra

def analyze_rectified(rectified_bgr: np.ndarray) -> AnalysisResult:
    boxes = find_top_result_boxes(rectified_bgr)
    elong_box = boxes[1]
    max_box = boxes[-1]

    graph = find_graph_plot(rectified_bgr)
    xmin, xmax, ymin, ymax = estimate_axis_limits(rectified_bgr, graph)
    curve = extract_green_curve(rectified_bgr, graph, xmin, xmax, ymin, ymax)
    break_x_est, max_y_est = curve_break_estimates(curve)
    test_datetime, datetime_note = detect_screen_datetime(rectified_bgr)

    elong_roi, max_roi = result_number_rois(rectified_bgr)

    elong, elong_txt, elong_note = template_recognize_colored_number(
        rectified_bgr[elong_roi.as_slice()],
        "green",
        expected_range=(0.0, max(20.0, xmax * 2.0)),
        decimal_places=2,
        expected_integer_digits=1,
    )

    maxforce, max_txt, max_note = template_recognize_colored_number(
        rectified_bgr[max_roi.as_slice()],
        "purple",
        expected_range=(0.0, max(10000.0, ymax * 2.0)),
        decimal_places=2,
        expected_integer_digits=2,
    )

    # Last-resort fallbacks. These are less exact than the display values, but
    # avoid nonsensical OCR such as 198222 or 2.7.
    if elong is None or (break_x_est is not None and elong > max(20.0, 5.0 * break_x_est)):
        elong = break_x_est
        elong_note = "curve fallback"

    if maxforce is None or (max_y_est is not None and maxforce < 0.20 * max_y_est):
        maxforce = max_y_est
        max_note = "curve fallback"

    return AnalysisResult(
        elong_box=elong_box,
        maxforce_box=max_box,
        graph_plot=graph,
        graph_corners=graph_corners_from_rect(graph),
        elongation=elong,
        max_force=maxforce,
        elongation_source=elong_note,
        max_force_source=max_note,
        x_min=xmin, x_max=xmax, y_min=ymin, y_max=ymax,
        curve_xy=curve,
        test_datetime=test_datetime or "",
        test_datetime_source=datetime_note,
    )



def graph_data_to_pixel(result: AnalysisResult, xval: float, yval: float) -> Optional[tuple[int, int]]:
    if result.graph_plot is None:
        return None
    if not (result.x_max > result.x_min and result.y_max > result.y_min):
        return None

    u = (float(xval) - result.x_min) / (result.x_max - result.x_min)
    v = (result.y_max - float(yval)) / (result.y_max - result.y_min)
    if result.graph_corners is not None:
        q = order_quad(np.asarray(result.graph_corners, dtype=np.float32).reshape(4, 2))
        src = np.array([[[u, v]]], dtype=np.float32)
        unit = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32)
        matrix = cv2.getPerspectiveTransform(unit, q)
        mapped = cv2.perspectiveTransform(src, matrix)[0, 0]
        return int(round(float(mapped[0]))), int(round(float(mapped[1])))

    r = result.graph_plot
    px = r.x1 + u * max(r.width - 1, 1)
    py = r.y1 + v * max(r.height - 1, 1)
    return int(round(px)), int(round(py))

def draw_curve_overlay(out: np.ndarray, result: AnalysisResult) -> None:
    if result.graph_plot is None:
        return
    r = result.graph_plot
    q = order_quad(result.graph_corners) if result.graph_corners is not None else graph_corners_from_rect(r)
    thickness = max(2, int(round(out.shape[1] / 1200)))
    if result.curve_xy is not None and len(result.curve_xy) >= 2 and result.x_max > result.x_min and result.y_max > result.y_min:
        pts = []
        for x, y in result.curve_xy:
            p = graph_data_to_pixel(result, float(x), float(y))
            if p is None:
                continue
            px, py = p
            if r.x1-5 <= px <= r.x2+5 and r.y1-5 <= py <= r.y2+5:
                pts.append([px, py])
        if len(pts) >= 2:
            arr = np.asarray(pts, dtype=np.int32).reshape(-1, 1, 2)
            cv2.polylines(out, [arr], False, (0, 0, 0), thickness + 3, cv2.LINE_AA)
            cv2.polylines(out, [arr], False, (0, 0, 255), thickness, cv2.LINE_AA)
            x0, y0 = pts[min(10, len(pts)-1)]
            cv2.putText(out, "Extracted curve", (x0 + 8, max(20, y0 - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, max(.45, out.shape[1]/2600),
                        (0, 0, 255), max(1, thickness), cv2.LINE_AA)
    if result.modulus_line is not None:
        x1, y1, x2, y2 = result.modulus_line
        p1 = graph_data_to_pixel(result, x1, y1)
        p2 = graph_data_to_pixel(result, x2, y2)
        if p1 and p2:
            cv2.line(out, p1, p2, (0, 0, 0), thickness + 4, cv2.LINE_AA)
            cv2.line(out, p1, p2, (255, 255, 0), thickness + 1, cv2.LINE_AA)
            cv2.putText(out, "Elastic slope", (p2[0] + 8, max(r.y1 + 18, p2[1] - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, max(.45, out.shape[1]/2600),
                        (255, 255, 0), max(1, thickness), cv2.LINE_AA)
    if result.break_line_x is not None and result.x_min <= result.break_line_x <= result.x_max:
        p_bottom = graph_data_to_pixel(result, result.break_line_x, result.y_min)
        p_top = graph_data_to_pixel(result, result.break_line_x, result.y_max)
        if p_bottom and p_top:
            cv2.line(out, p_bottom, p_top, (0, 0, 0), thickness + 3, cv2.LINE_AA)
            cv2.line(out, p_bottom, p_top, (0, 255, 255), thickness, cv2.LINE_AA)
            break_text = f"Break {result.break_line_x:.2f} mm" + (" (manual)" if result.break_is_manual else "")
            cv2.putText(out, break_text, (p_top[0] + 8, max(24, p_top[1] + 28)),
                        cv2.FONT_HERSHEY_SIMPLEX, max(.45, out.shape[1]/2600),
                        (0, 255, 255), max(1, thickness), cv2.LINE_AA)

    # Mark the detected data-axis min/max grid intersections so the user can
    # see exactly which gridlines are used for scaling.
    if result.x_max > result.x_min and result.y_max > result.y_min:
        axis_points = [
            (result.x_min, result.y_min, "x/y min"),
            (result.x_max, result.y_min, "x max"),
            (result.x_min, result.y_max, "y max"),
            (result.x_max, result.y_max, "max/max"),
        ]
        for xv, yv, label in axis_points:
            p = graph_data_to_pixel(result, xv, yv)
            if p is None:
                continue
            cv2.circle(out, p, max(5, thickness + 3), (0, 0, 0), -1, cv2.LINE_AA)
            cv2.circle(out, p, max(3, thickness + 1), (255, 255, 255), -1, cv2.LINE_AA)
        p0 = graph_data_to_pixel(result, result.x_min, result.y_min)
        p1 = graph_data_to_pixel(result, result.x_max, result.y_min)
        p2 = graph_data_to_pixel(result, result.x_min, result.y_max)
        if p0:
            cv2.putText(out, f"({result.x_min:g}, {result.y_min:g})", (p0[0] + 8, max(r.y1+18, p0[1] - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, max(.40, out.shape[1]/3000), (255,255,255), max(1, thickness), cv2.LINE_AA)
        if p1:
            cv2.putText(out, f"x max {result.x_max:g}", (max(r.x1+5, p1[0] - 120), max(r.y1+18, p1[1] - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, max(.40, out.shape[1]/3000), (255,255,255), max(1, thickness), cv2.LINE_AA)
        if p2:
            cv2.putText(out, f"y max {result.y_max:g}", (p2[0] + 8, p2[1] + 22),
                        cv2.FONT_HERSHEY_SIMPLEX, max(.40, out.shape[1]/3000), (255,255,255), max(1, thickness), cv2.LINE_AA)



def _nice_axis_max(value: float, minimum: float = 1.0) -> float:
    """Round a positive axis maximum upwards to a readable 1/2/5×10^n value."""
    value = max(float(value), float(minimum))
    if not np.isfinite(value) or value <= 0:
        return minimum
    exp = math.floor(math.log10(value))
    base = 10 ** exp
    for m in (1, 1.2, 1.5, 2, 3, 5, 6, 8, 10):
        if value <= m * base + 1e-12:
            return float(m * base)
    return float(10 * base)


def _draw_dashed_vline(img: np.ndarray, x: int, y1: int, y2: int, color, thickness: int = 2,
                       dash: int = 14, gap: int = 9) -> None:
    y = y1
    while y < y2:
        cv2.line(img, (x, y), (x, min(y + dash, y2)), color, thickness, cv2.LINE_AA)
        y += dash + gap


def _pil_font(size: int, bold: bool = False):
    """Load a pleasant TrueType font on Windows, macOS, or Linux."""
    candidates = []
    if sys.platform.startswith("win"):
        candidates += [
            r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf",
            r"C:\Windows\Fonts\calibrib.ttf" if bold else r"C:\Windows\Fonts\calibri.ttf",
            r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        ]
    elif sys.platform == "darwin":
        candidates += [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/SFNS.ttf",
        ]
    candidates += [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for p in candidates:
        try:
            if p and Path(p).exists():
                return ImageFont.truetype(p, size=size)
        except Exception:
            pass
    try:
        return ImageFont.truetype("arial.ttf", size=size)
    except Exception:
        return ImageFont.load_default()


def _text_bbox(draw: ImageDraw.ImageDraw, xy, text: str, font) -> tuple[int, int, int, int]:
    try:
        return draw.textbbox(xy, text, font=font)
    except Exception:
        w, h = draw.textsize(text, font=font)
        return (int(xy[0]), int(xy[1]), int(xy[0] + w), int(xy[1] + h))


def _draw_right_text(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, font, fill) -> None:
    b = _text_bbox(draw, (0, 0), text, font)
    draw.text((x - (b[2] - b[0]), y), text, font=font, fill=fill)


def _draw_center_text(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, font, fill) -> None:
    b = _text_bbox(draw, (0, 0), text, font)
    draw.text((x - (b[2] - b[0]) // 2, y), text, font=font, fill=fill)


def _draw_dashed_line_pil(draw: ImageDraw.ImageDraw, xy1: tuple[int, int], xy2: tuple[int, int], fill,
                          width: int = 2, dash: int = 12, gap: int = 8) -> None:
    x1, y1 = xy1
    x2, y2 = xy2
    if x1 == x2:
        y = min(y1, y2)
        end = max(y1, y2)
        while y < end:
            draw.line((x1, y, x2, min(y + dash, end)), fill=fill, width=width)
            y += dash + gap
    else:
        draw.line((x1, y1, x2, y2), fill=fill, width=width)


def draw_analysis_graph(result: AnalysisResult,
                        gauge_length_mm: float = 50.0,
                        sample_width_mm: float = 15.0,
                        thickness_um: Optional[float] = None,
                        grammage_g_m2: Optional[float] = 100.0,
                        width: int = 1500,
                        height: int = 860) -> tuple[np.ndarray, dict]:
    """Create a clean generated Force-vs-tensile-strain graph using TrueType fonts."""
    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)

    title_font = _pil_font(30, True)
    subtitle_font = _pil_font(19, False)
    axis_font = _pil_font(18, True)
    tick_font = _pil_font(15, False)
    small_font = _pil_font(15, False)
    small_bold = _pil_font(15, True)
    table_head_font = _pil_font(20, True)
    table_font = _pil_font(14, False)
    table_bold = _pil_font(14, True)

    margin_left, margin_right = 105, 42
    margin_top, margin_bottom = 205, 92
    table_w = 430
    plot = Rect(margin_left, margin_top, width - margin_right - table_w - 30, height - margin_bottom)
    table = Rect(plot.x2 + 26, margin_top, width - margin_right, plot.y2)

    curve = prepare_curve_for_mechanics(result.curve_xy)
    if gauge_length_mm <= 0:
        gauge_length_mm = 50.0
    if len(curve) >= 2:
        xp = curve[:, 0] / gauge_length_mm * 100.0
        yf = curve[:, 1]
    else:
        xp = np.asarray([], dtype=float)
        yf = np.asarray([], dtype=float)

    # Display about 30 % headroom beyond the actual extracted data.
    # The top axis is extension [mm], while the bottom axis is the equivalent
    # tensile strain [%].
    if len(curve):
        largest_extension_mm = float(np.nanmax(curve[:, 0]))
    elif result.elongation_data is not None:
        largest_extension_mm = float(result.elongation_data)
    elif result.elongation is not None:
        largest_extension_mm = float(result.elongation)
    else:
        largest_extension_mm = 5.0

    raw_x_max_mm = max(0.1, largest_extension_mm * 1.30)
    x_nice_step_mm = 0.25 if raw_x_max_mm <= 3.0 else 0.5 if raw_x_max_mm <= 6.0 else 1.0
    x_max_mm = float(math.ceil(raw_x_max_mm / x_nice_step_mm) * x_nice_step_mm)
    x_min_pct = 0.0
    x_max_pct = x_max_mm / gauge_length_mm * 100.0

    force_candidates = []
    if len(yf):
        force_candidates.append(float(np.nanmax(yf)))
    if result.max_force is not None:
        force_candidates.append(float(result.max_force))
    if result.max_force_data is not None:
        force_candidates.append(float(result.max_force_data))
    peak_for_axis = max(force_candidates) if force_candidates else 120.0
    raw_y_max = max(1.0, peak_for_axis * 1.30)
    y_step_nice = 5.0 if raw_y_max <= 80 else 10.0 if raw_y_max <= 200 else 20.0
    y_min = 0.0
    y_max = float(math.ceil(raw_y_max / y_step_nice) * y_step_nice)

    def px(xpct: float) -> int:
        return int(round(plot.x1 + (xpct - x_min_pct) / max(x_max_pct - x_min_pct, 1e-9) * plot.width))

    def py(force: float) -> int:
        return int(round(plot.y2 - (force - y_min) / max(y_max - y_min, 1e-9) * plot.height))

    # Background, title and tester timestamp
    draw.rectangle((0, 0, width, height), fill=(255, 255, 255))
    draw.text((margin_left, 24), "YDL-7003-P tensile test result", font=title_font, fill=(25, 25, 25))
    datetime_text = result.test_datetime or "Date and time not detected"
    draw.text((margin_left, 64), f"Test date and time: {datetime_text}",
              font=subtitle_font, fill=(45, 45, 45))
    draw.text((margin_left, 94), "Force vs. tensile strain (%)",
              font=subtitle_font, fill=(85, 85, 85))

    # Plot background
    draw.rectangle((plot.x1, plot.y1, plot.x2, plot.y2), fill=(252, 252, 252), outline=(30, 30, 30), width=2)

    # Choose tick spacing dynamically. With the default 50 mm gauge length,
    # tensile strains are often only 1–5 %, so the old 10 %-tick spacing gave
    # too few labels. This gives more x-axis labels without overcrowding.
    if x_max_pct <= 2.0:
        x_step = 0.2
    elif x_max_pct <= 5.0:
        x_step = 0.5
    elif x_max_pct <= 10.0:
        x_step = 1.0
    elif x_max_pct <= 20.0:
        x_step = 2.0
    elif x_max_pct <= 50.0:
        x_step = 5.0
    elif x_max_pct <= 100.0:
        x_step = 10.0
    elif x_max_pct <= 200.0:
        x_step = 20.0
    else:
        x_step = 50.0
    y_step = 10.0 if y_max <= 120 else 20.0 if y_max <= 240 else 50.0
    minor_x = x_step / 2.0
    minor_y = y_step / 2.0

    def fmt_tick(v: float) -> str:
        if abs(v - round(v)) < 1e-9:
            return f"{int(round(v))}"
        return f"{v:.1f}".rstrip("0").rstrip(".")

    def fmt_extension_tick(v: float) -> str:
        if abs(v - round(v)) < 1e-9:
            return f"{int(round(v))}"
        if abs(v * 10.0 - round(v * 10.0)) < 1e-9:
            return f"{v:.1f}".rstrip("0").rstrip(".")
        return f"{v:.2f}".rstrip("0").rstrip(".")

    # Minor grid, including vertical grid lines.
    tick = minor_x
    while tick < x_max_pct - 1e-9:
        xpix = px(tick)
        draw.line((xpix, plot.y1, xpix, plot.y2), fill=(224, 224, 224), width=1)
        tick += minor_x
    tick = minor_y
    while tick < y_max - 1e-9:
        ypix = py(tick)
        draw.line((plot.x1, ypix, plot.x2, ypix), fill=(226, 226, 226), width=1)
        tick += minor_y

    # Major grid and labels.
    x_tick = 0.0
    while x_tick <= x_max_pct + 1e-9:
        xpix = px(x_tick)
        draw.line((xpix, plot.y1, xpix, plot.y2), fill=(178, 178, 178), width=2)
        draw.line((xpix, plot.y2, xpix, plot.y2 + 7), fill=(0, 0, 0), width=1)
        _draw_center_text(draw, xpix, plot.y2 + 12, fmt_tick(x_tick), tick_font, (45, 45, 45))

        # Secondary top axis: the same x positions expressed as extension in mm.
        extension_mm = x_tick * gauge_length_mm / 100.0
        draw.line((xpix, plot.y1 - 7, xpix, plot.y1), fill=(0, 0, 0), width=1)
        _draw_center_text(
            draw, xpix, plot.y1 - 31, fmt_extension_tick(extension_mm),
            tick_font, (45, 45, 45)
        )
        x_tick += x_step
    y_tick = 0.0
    while y_tick <= y_max + 1e-9:
        ypix = py(y_tick)
        draw.line((plot.x1, ypix, plot.x2, ypix), fill=(178, 178, 178), width=2)
        draw.line((plot.x1 - 7, ypix, plot.x1, ypix), fill=(0, 0, 0), width=1)
        _draw_right_text(draw, plot.x1 - 12, ypix - 8, fmt_tick(y_tick), tick_font, (45, 45, 45))
        y_tick += y_step
    draw.rectangle((plot.x1, plot.y1, plot.x2, plot.y2), outline=(30, 30, 30), width=2)
    _draw_center_text(
        draw, plot.x1 + plot.width // 2, plot.y1 - 60,
        "Extension (mm)", axis_font, (0, 0, 0)
    )
    _draw_center_text(
        draw, plot.x1 + plot.width // 2, height - 50,
        "Tensile strain (%)", axis_font, (0, 0, 0)
    )

    # Draw the force-axis title vertically and centre it beside the y axis.
    force_label = "Force (N)"
    bbox = _text_bbox(draw, (0, 0), force_label, axis_font)
    label_w = max(1, bbox[2] - bbox[0] + 12)
    label_h = max(1, bbox[3] - bbox[1] + 12)
    label_img = Image.new("RGBA", (label_w, label_h), (255, 255, 255, 0))
    label_draw = ImageDraw.Draw(label_img)
    label_draw.text((6 - bbox[0], 6 - bbox[1]), force_label, font=axis_font, fill=(0, 0, 0, 255))
    label_img = label_img.rotate(90, expand=True, resample=Image.Resampling.BICUBIC)
    label_x = max(8, plot.x1 - 82)
    label_y = plot.y1 + (plot.height - label_img.height) // 2
    image.paste(label_img, (label_x, label_y), label_img)

    # Curve
    if len(xp) >= 2:
        pts = []
        for xval, yval in zip(xp, yf):
            if np.isfinite(xval) and np.isfinite(yval):
                pts.append((int(np.clip(px(float(xval)), plot.x1, plot.x2)),
                            int(np.clip(py(float(yval)), plot.y1, plot.y2))))
        if len(pts) >= 2:
            draw.line(pts, fill=(0, 0, 0), width=6, joint="curve")
            draw.line(pts, fill=(235, 105, 20), width=3, joint="curve")

    # Elastic slope line
    if result.modulus_line is not None:
        x1, y1, x2, y2 = result.modulus_line
        p1 = (px(100.0 * x1 / gauge_length_mm), py(y1))
        p2 = (px(100.0 * x2 / gauge_length_mm), py(y2))
        draw.line((p1[0], p1[1], p2[0], p2[1]), fill=(0, 0, 0), width=6)
        draw.line((p1[0], p1[1], p2[0], p2[1]), fill=(0, 90, 180), width=3)
        draw.text((min(p2[0] + 8, plot.x2 - 120), max(plot.y1 + 12, p2[1] - 26)),
                  "modulus fit", font=small_bold, fill=(0, 80, 165))

    # Break elongation lines
    if result.elongation_data_percent is not None:
        xpix = px(result.elongation_data_percent)
        if plot.x1 <= xpix <= plot.x2:
            draw.line((xpix, plot.y1, xpix, plot.y2), fill=(0, 0, 0), width=5)
            draw.line((xpix, plot.y1, xpix, plot.y2), fill=(10, 160, 150), width=3)
            break_caption = "curve break extension (manual)" if result.break_is_manual else "curve break extension"
            draw.text((xpix + 8, plot.y1 + 18), break_caption, font=small_bold, fill=(0, 120, 115))
    if result.elongation_text_percent is not None:
        xpix = px(result.elongation_text_percent)
        if plot.x1 <= xpix <= plot.x2:
            _draw_dashed_line_pil(draw, (xpix, plot.y1), (xpix, plot.y2), fill=(30, 150, 60), width=2)
            draw.text((xpix + 8, plot.y1 + 44), "instrument extension", font=small_font, fill=(25, 125, 45))

    # Results table
    draw.rectangle((table.x1, table.y1, table.x2, table.y2), fill=(248, 250, 252), outline=(130, 130, 130), width=1)
    draw.rectangle((table.x1, table.y1, table.x2, table.y1 + 42), fill=(232, 240, 247), outline=(130, 130, 130), width=1)
    draw.text((table.x1 + 14, table.y1 + 10), "Parameters", font=table_head_font, fill=(30, 30, 30))

    def fmtv(v, nd=3):
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            return "-"
        return f"{v:.{nd}g}"

    def fmt_fixed_graph(v, nd=2):
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            return "-"
        return f"{v:.{nd}f}"

    rows = [
        ("Instrument extension", f"{fmt_fixed_graph(result.elongation)} mm"),
        ("Instrument strain", f"{fmt_fixed_graph(result.elongation_text_percent)} %"),
        (
            "Curve break extension",
            f"{fmt_fixed_graph(result.elongation_data)} mm"
            + (" (manual)" if result.break_is_manual else "")
        ),
        (
            "Curve strain at break",
            f"{fmt_fixed_graph(result.elongation_data_percent)} %"
            + (" (manual)" if result.break_is_manual else "")
        ),
        ("Instrument max force", f"{fmt_fixed_graph(result.max_force)} N"),
        ("Curve maximum force", f"{fmt_fixed_graph(result.max_force_data)} N"),
        ("Initial slope", f"{fmtv(result.elastic_slope_n_per_mm)} N/mm"),
        ("Fit R²", fmtv(result.modulus_r2, 4)),
        ("Tensile stiffness", f"{fmtv(result.tensile_stiffness_kn_per_m)} kN/m"),
        ("Stiffness index", f"{fmtv(result.tensile_stiffness_index_knm_per_kg)} kN·m/kg"),
        ("Tensile modulus", f"{fmtv(result.elastic_modulus_mpa)} MPa"),
        ("Tensile energy", f"{fmtv(result.toughness_n_mm)} N·mm ({fmtv(result.toughness_mj)} mJ)"),
    ]
    yrow = table.y1 + 58
    row_h = 31
    for name, value in rows:
        draw.line((table.x1, yrow - 10, table.x2, yrow - 10), fill=(224, 224, 224), width=1)
        draw.text((table.x1 + 14, yrow), name, font=table_font, fill=(75, 75, 75))
        draw.text((table.x1 + 220, yrow), value, font=table_bold, fill=(15, 15, 15))
        yrow += row_h

    if result.mechanical_note:
        note_font = _pil_font(12, False)
        note = "Note: " + result.mechanical_note
        words = note.split()
        lines = []
        current = ""
        max_w = table.width - 28
        for word in words:
            trial = (current + " " + word).strip()
            b = _text_bbox(draw, (0, 0), trial, note_font)
            if b[2] - b[0] <= max_w:
                current = trial
            else:
                if current:
                    lines.append(current)
                current = word
            if len(lines) >= 2:
                break
        if current and len(lines) < 3:
            lines.append(current)
        if lines:
            note_y = min(table.y2 - 14 * len(lines) - 10, yrow + 8)
            note_y = max(yrow + 4, note_y)
            for line in lines[:3]:
                draw.text((table.x1 + 14, note_y), line, font=note_font, fill=(140, 0, 0))
                note_y += 14

    # Legend
    legend_y = 132
    draw.line((plot.x1, legend_y, plot.x1 + 42, legend_y), fill=(235, 105, 20), width=4)
    draw.text((plot.x1 + 50, legend_y - 10), "curve", font=small_font, fill=(60, 60, 60))
    draw.line((plot.x1 + 122, legend_y, plot.x1 + 164, legend_y), fill=(0, 90, 180), width=4)
    draw.text((plot.x1 + 172, legend_y - 10), "modulus fit", font=small_font, fill=(60, 60, 60))
    draw.line((plot.x1 + 290, legend_y - 15, plot.x1 + 290, legend_y + 15), fill=(10, 160, 150), width=4)
    legend_break = "break extension (manual)" if result.break_is_manual else "break extension"
    draw.text((plot.x1 + 300, legend_y - 10), legend_break, font=small_font, fill=(60, 60, 60))

    meta = {
        "plot": plot,
        "x_min_pct": x_min_pct,
        "x_max_pct": x_max_pct,
        "x_max_mm": x_max_mm,
        "y_min": y_min,
        "y_max": y_max,
    }
    rgb = np.asarray(image, dtype=np.uint8)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), meta


def _fit_pil_image(img: Image.Image, box_w: int, box_h: int) -> tuple[Image.Image, int, int]:
    """Resize PIL image to fit a box, preserving aspect ratio."""
    if img.width <= 0 or img.height <= 0:
        return img, 0, 0
    scale = min(box_w / img.width, box_h / img.height)
    new_w = max(1, int(round(img.width * scale)))
    new_h = max(1, int(round(img.height * scale)))
    return img.resize((new_w, new_h), Image.Resampling.LANCZOS), new_w, new_h


def _draw_pdf_header(draw: ImageDraw.ImageDraw, page_w: int, title: str,
                     subtitle: str, y: int = 34) -> int:
    title_font = _pil_font(34, True)
    subtitle_font = _pil_font(17, False)
    draw.text((60, y), title, font=title_font, fill=(25, 25, 25))
    if subtitle:
        draw.text((60, y + 42), subtitle, font=subtitle_font, fill=(85, 85, 85))
    draw.line((60, y + 76, page_w - 60, y + 76), fill=(210, 210, 210), width=2)
    return y + 96


def _make_pdf_image_page(image_bgr: np.ndarray, title: str, subtitle: str,
                         page_w: int = 1754, page_h: int = 1240) -> Image.Image:
    """Create a landscape A4-like raster page containing one image."""
    page = Image.new("RGB", (page_w, page_h), (255, 255, 255))
    draw = ImageDraw.Draw(page)
    top = _draw_pdf_header(draw, page_w, title, subtitle)
    footer_font = _pil_font(12, False)
    footer = "YDL-7003-P data analyzer"
    b = _text_bbox(draw, (0, 0), footer, footer_font)
    draw.text((page_w - 60 - (b[2] - b[0]), page_h - 34), footer, font=footer_font, fill=(110, 110, 110))
    draw.line((60, page_h - 48, page_w - 60, page_h - 48), fill=(230, 230, 230), width=1)

    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(rgb)
    box_w = page_w - 120
    box_h = page_h - top - 82
    img_fit, iw, ih = _fit_pil_image(img, box_w, box_h)
    x = (page_w - iw) // 2
    y = top + max(0, (box_h - ih) // 2)
    page.paste(img_fit, (x, y))
    draw.rectangle((x, y, x + iw, y + ih), outline=(180, 180, 180), width=1)
    return page


def export_analysis_pdf(path: str | Path, source_path: Optional[Path],
                        analysis_graph_bgr: Optional[np.ndarray],
                        annotated_screen_bgr: Optional[np.ndarray],
                        test_datetime: str = "") -> None:
    """
    Export a compact PDF report.

    The first page is the generated analysis graph, which contains the curve,
    modulus fit, break marker, and parameter table. The second page is the
    perspective-corrected display with the extraction overlay.
    """
    if analysis_graph_bgr is None or analysis_graph_bgr.size == 0:
        raise RuntimeError("The analysis graph is not available.")
    source = source_path.name if source_path else ""
    subtitle_parts = []
    if source:
        subtitle_parts.append(f"Source image: {source}")
    if test_datetime:
        subtitle_parts.append(f"Test date and time: {test_datetime}")
    subtitle = "  |  ".join(subtitle_parts)

    pages: list[Image.Image] = [
        _make_pdf_image_page(analysis_graph_bgr, "YDL-7003-P tensile test result", subtitle)
    ]
    if annotated_screen_bgr is not None and annotated_screen_bgr.size:
        pages.append(_make_pdf_image_page(
            annotated_screen_bgr,
            "Perspective-corrected screen and extracted curve",
            subtitle,
        ))

    pages[0].save(
        str(path),
        "PDF",
        resolution=150.0,
        save_all=True,
        append_images=pages[1:],
    )


def draw_annotations(image_bgr: np.ndarray, result: AnalysisResult) -> np.ndarray:
    out = image_bgr.copy()

    def box(rect: Optional[Rect], color, label):
        if not rect:
            return
        thickness = max(2, int(round(out.shape[1]/900)))
        cv2.rectangle(out, (rect.x1,rect.y1), (rect.x2,rect.y2), color, thickness)
        cv2.putText(
            out, label, (rect.x1, max(20, rect.y1-8)),
            cv2.FONT_HERSHEY_SIMPLEX, max(.6, out.shape[1]/1900),
            color, thickness, cv2.LINE_AA
        )

    ev = "Instrument extension" if result.elongation is None else f"Instrument extension: {result.elongation:.2f} mm"
    fv = "Instrument maximum force" if result.max_force is None else f"Instrument max force: {result.max_force:.2f} N"
    box(result.elong_box, (0,255,255), ev)
    box(result.maxforce_box, (255,0,255), fv)
    graph_label = f"Graph x={result.x_min:g}..{result.x_max:g} mm, y={result.y_min:g}..{result.y_max:g} N"
    if result.graph_corners is not None:
        q = order_quad(np.asarray(result.graph_corners, dtype=np.float32).reshape(4, 2))
        pts = np.round(q).astype(np.int32).reshape(-1, 1, 2)
        thickness = max(2, int(round(out.shape[1]/900)))
        cv2.polylines(out, [pts], True, (0,165,255), thickness, cv2.LINE_AA)
        x0, y0 = int(q[0, 0]), int(q[0, 1])
        cv2.putText(out, graph_label, (x0, max(20, y0-8)),
                    cv2.FONT_HERSHEY_SIMPLEX, max(.6, out.shape[1]/1900),
                    (0,165,255), thickness, cv2.LINE_AA)
    else:
        box(result.graph_plot, (0,165,255), graph_label)
    draw_curve_overlay(out, result)
    return out

def _col_name(n: int) -> str:
    name = ""
    while n:
        n, r = divmod(n - 1, 26)
        name = chr(65 + r) + name
    return name


def _xml_escape(value) -> str:
    text = "" if value is None else str(value)
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;"))


def _xlsx_cell(value, row: int, col: int, style: int = 0) -> str:
    ref = f"{_col_name(col)}{row}"
    s_attr = f' s="{style}"' if style else ""
    if value is None or value == "":
        return f'<c r="{ref}"{s_attr}/>'
    if isinstance(value, (int, float, np.integer, np.floating)) and np.isfinite(value):
        return f'<c r="{ref}"{s_attr}><v>{float(value):.12g}</v></c>'
    return f'<c r="{ref}" t="inlineStr"{s_attr}><is><t>{_xml_escape(value)}</t></is></c>'


def _sheet_xml(rows: list[list], widths: Optional[list[float]] = None, drawing_rid: Optional[str] = None) -> str:
    max_cols = max((len(r) for r in rows), default=1)
    dim = f"A1:{_col_name(max_cols)}{max(1, len(rows))}"
    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">',
        f'<dimension ref="{dim}"/>'
    ]
    if widths:
        parts.append('<cols>')
        for i, width in enumerate(widths, 1):
            parts.append(f'<col min="{i}" max="{i}" width="{width}" customWidth="1"/>')
        parts.append('</cols>')
    parts.append('<sheetData>')
    for r_idx, row in enumerate(rows, 1):
        parts.append(f'<row r="{r_idx}">')
        for c_idx, value in enumerate(row, 1):
            style = 1 if r_idx == 1 else (2 if isinstance(value, (int, float, np.integer, np.floating)) else 0)
            parts.append(_xlsx_cell(value, r_idx, c_idx, style))
        parts.append('</row>')
    parts.append('</sheetData>')
    if drawing_rid:
        parts.append(f'<drawing r:id="{drawing_rid}"/>')
    parts.append('</worksheet>')
    return "".join(parts)


def export_analysis_xlsx(path: str | Path, result: AnalysisResult, source_path: Optional[Path],
                         gauge_length_mm: float, sample_width_mm: float,
                         thickness_um: Optional[float], grammage_g_m2: Optional[float],
                         graph_image_bgr: Optional[np.ndarray] = None) -> None:
    """Write a multi-sheet .xlsx report and embed the generated analysis graph."""
    path = Path(path)
    rows_summary = [
        ["YDL-7003-P data analyzer", ""],
        ["Source image", source_path.name if source_path else ""],
        ["Test date and time", result.test_datetime or "Not detected"],
        ["Gauge length / test length", gauge_length_mm, "mm"],
        ["Sample width", sample_width_mm, "mm"],
        ["Thickness", thickness_um if thickness_um is not None else "", "µm"],
        ["Grammage", grammage_g_m2 if grammage_g_m2 is not None else "", "g/m²"],
        ["", ""],
        ["Result", "Value", "Unit", "Source/notes"],
        ["Extension at break from instrument output", result.elongation, "mm", result.elongation_source],
        ["Tensile strain at break from instrument output", result.elongation_text_percent, "%", "extension / gauge length"],
        [
            "Extension at break from extracted curve" + (" (manual)" if result.break_is_manual else ""),
            result.elongation_data,
            "mm",
            "manually selected from analysis graph" if result.break_is_manual else "detected from extracted curve",
        ],
        [
            "Tensile strain at break from extracted curve" + (" (manual)" if result.break_is_manual else ""),
            result.elongation_data_percent,
            "%",
            "manual extension / gauge length" if result.break_is_manual else "extension / gauge length",
        ],
        ["Maximum force from instrument output", result.max_force, "N", result.max_force_source],
        ["Maximum force from extracted curve", result.max_force_data, "N", "maximum of extracted curve"],
        ["Initial force-extension slope", result.elastic_slope_n_per_mm, "N/mm", f"linear fit R²={result.modulus_r2:.4f}" if result.modulus_r2 is not None else ""],
        ["Tensile stiffness", result.tensile_stiffness_kn_per_m, "kN/m", "slope × gauge length / width"],
        ["Tensile stiffness index", result.tensile_stiffness_index_knm_per_kg, "kN·m/kg", "requires grammage"],
        ["Tensile modulus", result.elastic_modulus_mpa, "MPa", "requires thickness"],
        ["Tensile energy / area under curve", result.toughness_n_mm, "N·mm", "to curve-derived break extension"],
        ["Tensile energy / area under curve", result.toughness_mj, "mJ", "1 N·mm = 1 mJ"],
        ["Axis x min", result.x_min, "mm", "axis-grid marker on display graph"],
        ["Axis x max", result.x_max, "mm", "axis-grid marker on display graph"],
        ["Axis y min", result.y_min, "N", "axis-grid marker on display graph"],
        ["Axis y max", result.y_max, "N", "axis-grid marker on display graph"],
        ["Mechanical calculation note", result.mechanical_note, "", ""],
    ]
    curve = result.curve_xy if result.curve_xy is not None else np.empty((0,2))
    rows_curve = [["Extension_mm", "Tensile_strain_percent", "Force_N"]]
    for x, y in curve:
        pct = (float(x) / gauge_length_mm * 100.0) if gauge_length_mm and gauge_length_mm > 0 else ""
        rows_curve.append([float(x), pct, float(y)])
    rows_fit = [["Item", "x1_mm", "y1_N", "x2_mm", "y2_N"]]
    if result.modulus_line is not None:
        x1, y1, x2, y2 = result.modulus_line
        rows_fit.append(["Tensile modulus fit line", x1, y1, x2, y2])
    if result.break_line_x is not None:
        rows_fit.append([
            "Break-extension vertical line" + (" (manual)" if result.break_is_manual else ""),
            result.break_line_x, result.y_min, result.break_line_x, result.y_max
        ])
    rows_graph = [["Analysis graph"], ["The same generated graph shown in the GUI is embedded below."]]

    graph_png = None
    graph_w = graph_h = 0
    if graph_image_bgr is not None and graph_image_bgr.size:
        ok, buf = cv2.imencode(".png", graph_image_bgr)
        if ok:
            graph_png = bytes(buf)
            graph_h, graph_w = graph_image_bgr.shape[:2]

    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Default Extension="png" ContentType="image/png"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/worksheets/sheet3.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/worksheets/sheet4.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/drawings/drawing1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""
    workbook = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets>
<sheet name="Summary" sheetId="1" r:id="rId1"/>
<sheet name="Curve data" sheetId="2" r:id="rId2"/>
<sheet name="Graph markers" sheetId="3" r:id="rId3"/>
<sheet name="Analysis graph" sheetId="4" r:id="rId4"/>
</sheets>
</workbook>"""
    wb_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet3.xml"/>
<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet4.xml"/>
<Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""
    styles = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="1"><numFmt numFmtId="164" formatCode="0.000"/></numFmts>
<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFD9EAF7"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/><xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""

    sheet4_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/drawing1.xml"/>
</Relationships>"""
    drawing_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image1.png"/>
</Relationships>"""
    cx = int(graph_w * 9525)
    cy = int(graph_h * 9525)
    drawing = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<xdr:oneCellAnchor>
<xdr:from><xdr:col>0</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>3</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from>
<xdr:ext cx="{cx}" cy="{cy}"/>
<xdr:pic><xdr:nvPicPr><xdr:cNvPr id="1" name="Analysis graph"/><xdr:cNvPicPr/></xdr:nvPicPr><xdr:blipFill><a:blip r:embed="rId1"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill><xdr:spPr><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr></xdr:pic>
<xdr:clientData/>
</xdr:oneCellAnchor>
</xdr:wsDr>"""

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        z.writestr("xl/styles.xml", styles)
        z.writestr("xl/worksheets/sheet1.xml", _sheet_xml(rows_summary, [34, 16, 12, 44]))
        z.writestr("xl/worksheets/sheet2.xml", _sheet_xml(rows_curve, [18, 18, 14]))
        z.writestr("xl/worksheets/sheet3.xml", _sheet_xml(rows_fit, [24, 14, 14, 14, 14]))
        z.writestr("xl/worksheets/sheet4.xml", _sheet_xml(rows_graph, [28, 80], drawing_rid="rId1" if graph_png else None))
        if graph_png:
            z.writestr("xl/worksheets/_rels/sheet4.xml.rels", sheet4_rels)
            z.writestr("xl/drawings/drawing1.xml", drawing)
            z.writestr("xl/drawings/_rels/drawing1.xml.rels", drawing_rels)
            z.writestr("xl/media/image1.png", graph_png)

