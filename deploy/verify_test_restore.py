"""Exercise logical backup/restore only on the recorded disposable MySQL server."""
import argparse,json,os,secrets,subprocess
from pathlib import Path

def verify(folder):
    folder=Path(folder).resolve();state=json.loads((folder/'test-services.json').read_text())
    if state['directory']!=str(folder) or state.get('cleanedUp'):raise RuntimeError('active disposable environment required')
    client=['/data/anaconda3/bin/mysql','--no-defaults','--protocol=socket','--socket='+str(folder/'mysql.sock'),'-uroot','--batch','--skip-column-names']
    def query(sql,database=None):return subprocess.check_output(client+([] if database is None else [database])+['-e',sql],text=True).strip()
    if query('SELECT @@port')!='13317':raise RuntimeError('test MySQL port identity mismatch')
    database='railway_p1_restore_'+secrets.token_hex(4)
    tables=query('SHOW TABLES','railway_p0_test').splitlines()
    counts={table:int(query('SELECT COUNT(*) FROM `'+table+'`','railway_p0_test')) for table in tables}
    backup=folder/'verified-test-backup.sql'
    with backup.open('wb') as output:
        subprocess.run(['/data/anaconda3/bin/mysqldump','--no-defaults','--protocol=socket','--socket='+str(folder/'mysql.sock'),'-uroot','--single-transaction','--routines','--triggers','railway_p0_test'],stdout=output,check=True)
    backup.chmod(0o600);query('CREATE DATABASE '+database+' CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
    try:
        with backup.open('rb') as source:subprocess.run(client+[database],stdin=source,check=True)
        restored={table:int(query('SELECT COUNT(*) FROM `'+table+'`',database)) for table in tables}
        if restored!=counts:raise RuntimeError('restored counts mismatch')
        report={'verified':True,'tables':len(tables),'rows':sum(counts.values()),'backupBytes':backup.stat().st_size,'counts':counts}
        (folder/'restore-result.json').write_text(json.dumps(report,indent=2));print(json.dumps({key:report[key] for key in ('verified','tables','rows','backupBytes')}))
    finally:query('DROP DATABASE '+database)

if __name__=='__main__':
    os.umask(0o077);parser=argparse.ArgumentParser();parser.add_argument('--directory',required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]/'workspace/runtime/p0-reaudit'
    if root not in Path(args.directory).resolve().parents:raise SystemExit('disposable environment directory required')
    verify(args.directory)
