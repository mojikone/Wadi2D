"""The same variants with the Sea line moved 60 m inland. On the perimeter it missed cells: at 15 m half the water stayed on land."""
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
for n in ('t0_base','t1_rain228','t2_n060','t3_ggc','t4_dx15','t5_all'):
    j=json.loads((HERE/'jobs'/f'{n}.json').read_text(encoding='utf-8'))
    for b in j['boundaries']:
        b['coordinates']=[[x-60.0,y] for x,y in b['coordinates']]
    j['project']['name']=j['project']['name']+'_inset'
    (HERE/'jobs'/f'b_{n}.json').write_text(json.dumps(j,indent=1),encoding='utf-8')
