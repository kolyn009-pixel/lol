"""Exercise the deployment's exact three-way merge against temporary repositories."""
from pathlib import Path
import subprocess,tempfile,unittest,sys
import os

SCRIPT=Path(__file__).with_name('deploy_learning_20261012.sh').read_text()
MERGE=SCRIPT.split('python3 - "$REPO" "$BASE" "$TARGET" "$NEW" "$BACKUP" <<\'PY\'\n',1)[1].split('\nPY\n',1)[0]

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.repo=self.root/'repo';self.repo.mkdir();self.new=self.root/'stage';self.new.mkdir();self.backup=self.root/'backup';self.backup.mkdir()
        self.git('init','-q');self.git('config','user.name','Test');self.git('config','user.email','test@example.invalid')
        self.lines=[f'line {i}\n' for i in range(30)];self.before=''.join(self.lines);(self.repo/'code.py').write_text(self.before)
        self.git('add','.');self.git('commit','-qm','base');self.base=self.git('rev-parse','HEAD').strip()
        remote=self.lines.copy();remote[1]='remote update\n';self.after=''.join(remote);(self.repo/'code.py').write_text(self.after);(self.repo/'new.js').write_text('new feature\n')
        self.git('add','.');self.git('commit','-qm','target');self.target=self.git('rev-parse','HEAD').strip()
        (self.new/'code.py').write_text(self.before)
    def git(self,*args):return subprocess.check_output(['git','-C',str(self.repo),*args],text=True)
    def merge(self):return subprocess.run([sys.executable,'-c',MERGE,str(self.repo),self.base,self.target,str(self.new),str(self.backup)],capture_output=True,text=True)
    def test_clean_patch_and_new_file(self):
        result=self.merge();self.assertEqual(result.returncode,0,result.stderr);self.assertEqual((self.new/'code.py').read_text(),self.after);self.assertEqual((self.new/'new.js').read_text(),'new feature\n')
    def test_live_change_is_preserved(self):
        current=self.lines.copy();current[28]='server-only edit\n';(self.new/'code.py').write_text(''.join(current));result=self.merge();self.assertEqual(result.returncode,0,result.stderr)
        result=(self.new/'code.py').read_text();self.assertIn('remote update',result);self.assertIn('server-only edit',result)
    def test_conflict_aborts_and_keeps_live_file(self):
        current=self.lines.copy();current[1]='conflicting server edit\n';actual=''.join(current);(self.new/'code.py').write_text(actual);result=self.merge();self.assertNotEqual(result.returncode,0);self.assertIn('MERGE_CONFLICT',result.stderr);self.assertEqual((self.new/'code.py').read_text(),actual)
    def test_changed_symlink_does_not_write_external_file(self):
        outside=self.root/'outside';outside.write_text('private\n');(self.new/'code.py').unlink();(self.new/'code.py').symlink_to(outside);result=self.merge();self.assertNotEqual(result.returncode,0);self.assertEqual(outside.read_text(),'private\n')
    def test_existing_added_file_is_not_overwritten(self):
        (self.new/'new.js').write_text('server custom\n');result=self.merge();self.assertNotEqual(result.returncode,0);self.assertEqual((self.new/'new.js').read_text(),'server custom\n')

    def test_rollback_stops_new_processes_before_starting_old_release(self):
        old=self.root/'old';old.mkdir();current=self.root/'current';current.symlink_to(self.new)
        shim=self.root/'bin';shim.mkdir();log=self.root/'service.log'
        unit=shim/'systemctl';unit.write_text('#!/bin/sh\nprintf "%s %s\\n" "$1" "$(readlink -f "$MOCK_CURRENT")" >> "$MOCK_LOG"\n');unit.chmod(0o755)
        function='rollback_on_error() {\n'+SCRIPT.split('rollback_on_error() {\n',1)[1].split('\n}\n',1)[0]+'\n}\n'
        shell='set -Eeuo pipefail\nOLD=$1; CURRENT=$2; BACKUP=$3; SWITCHED=1; STOPPED=1; UNITS=(one two)\n'+function+'trap rollback_on_error ERR\nfalse\n'
        env={**os.environ,'PATH':str(shim)+':'+os.environ['PATH'],'MOCK_CURRENT':str(current),'MOCK_LOG':str(log)}
        result=subprocess.run(['bash','-c',shell,'test',str(old),str(current),str(self.backup)],env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,1);self.assertEqual(current.resolve(),old)
        self.assertEqual(log.read_text().splitlines(),['stop '+str(self.new),'start '+str(old)])

if __name__=='__main__':unittest.main()
