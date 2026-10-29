import json, os, stat, sys, tempfile, textwrap, unittest
from pathlib import Path

class AppServerTests(unittest.TestCase):
    def test_read_and_consume_over_stdio_jsonrpc(self):
        from codex_reset_guardian.appserver import CodexAppServer
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "fake_codex.py"
            fake.write_text(textwrap.dedent('''#!/usr/bin/env python3
import json,sys
for line in sys.stdin:
    msg=json.loads(line)
    if 'id' not in msg: continue
    method=msg['method']
    if method=='initialize': result={'ok':True}
    elif method=='account/rateLimits/read': result={'accountId':'acct','rateLimitResetCredits':{'availableCount':1,'credits':[]}}
    elif method=='account/rateLimitResetCredit/consume': result={'outcome':'reset'}
    else: result={}
    print(json.dumps({'jsonrpc':'2.0','id':msg['id'],'result':result}), flush=True)
'''))
            with CodexAppServer(command=[sys.executable,str(fake)]) as rpc:
                snap=rpc.request('account/rateLimits/read', {'excludeResetCreditDetails':False})
                out=rpc.request('account/rateLimitResetCredit/consume', {'creditId':'c1','idempotencyKey':'k'})
            self.assertEqual(snap['accountId'],'acct')
            self.assertEqual(out['outcome'],'reset')

class CodexPathResolutionTests(unittest.TestCase):
    def test_service_environment_path_wins_over_shell_lookup(self):
        from unittest.mock import patch
        from codex_reset_guardian.appserver import resolve_codex_path
        with patch.dict(os.environ,{'CODEX_RESET_GUARDIAN_CODEX':'/service/codex'}), patch('codex_reset_guardian.appserver.shutil.which',return_value='/shell/codex'):
            self.assertEqual(resolve_codex_path(),'/service/codex')

class CrossPlatformTransportTests(unittest.TestCase):
    def test_explicit_command_uses_cross_platform_subprocess_reader(self):
        import sys
        from codex_reset_guardian.appserver import CodexAppServer
        with tempfile.TemporaryDirectory() as td:
            script=Path(td)/'fake_codex.py'
            script.write_text(textwrap.dedent('''
import json,sys
for line in sys.stdin:
    msg=json.loads(line)
    if 'id' not in msg: continue
    if msg['method']=='initialize': result={}
    elif msg['method']=='ping': result={'pong':True}
    else: result={}
    print(json.dumps({'jsonrpc':'2.0','id':msg['id'],'result':result}),flush=True)
'''))
            with CodexAppServer(command=[sys.executable,str(script)]) as rpc:
                self.assertEqual(rpc.request('ping'),{'pong':True})
