"""Idempotent guarded MySQL indexes. Run only after the separate full backup."""
import argparse
from pathlib import Path
import subprocess

INDEXES={
    'camera':{'uq_camera_active_name':'UNIQUE (active_name)'},
    'abnormal_event':{'ix_p1_event_time':'(deleted,event_time,id)','ix_p1_camera_time':'(camera_id,deleted,event_time,id)','ix_p1_status_time':'(deleted,status,event_time,id)','ix_p1_created':'(deleted,create_time)'},
    'risk_track':{'ix_risk_track_alarm':'(alarm_id,state)'},'risk_incident':{'ix_risk_session':'(session_id,state)'},
}
def apply(client,expected_port):
    def query(sql):return subprocess.check_output(client+['-e',sql],text=True).strip()
    if query('SELECT @@port')!=str(expected_port):raise RuntimeError('Database port identity mismatch')
    if query("SELECT COUNT(*) FROM (SELECT LOWER(TRIM(name)) n FROM camera WHERE deleted=0 AND name IS NOT NULL GROUP BY LOWER(TRIM(name)) HAVING COUNT(*)>1) duplicates")!='0':raise RuntimeError('Active camera names conflict; preserve data and resolve explicitly before adding uniqueness')
    if query("SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='camera' AND column_name='active_name'")=='0':
        query('ALTER TABLE camera ADD COLUMN active_name VARCHAR(100) GENERATED ALWAYS AS (CASE WHEN deleted=0 THEN LOWER(TRIM(name)) ELSE NULL END)')
    applied=0
    for table,indexes in INDEXES.items():
        for name,columns in indexes.items():
            if query("SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='"+table+"' AND index_name='"+name+"'")!='0':continue
            unique=columns.startswith('UNIQUE ');columns=columns.removeprefix('UNIQUE ')
            query('CREATE '+('UNIQUE ' if unique else '')+'INDEX '+name+' ON '+table+columns);applied+=1
    return applied

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--socket',required=True);parser.add_argument('--database',choices=('railway_monitoring','railway_p0_test'),required=True);args=parser.parse_args()
    expected=3307 if args.database=='railway_monitoring' else 13317
    client=['/data/anaconda3/bin/mysql','--no-defaults','--protocol=socket','--socket='+str(Path(args.socket).resolve()),'-uroot','--batch','--skip-column-names',args.database]
    print('indexes applied:',apply(client,expected))
