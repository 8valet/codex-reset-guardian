import json, os, unittest

class Response:
    def __enter__(self): return self
    def __exit__(self,*_): pass
    def read(self): return b'{}'

class NotificationsTests(unittest.TestCase):
    def setUp(self):
        self.event={'severity':'warning','title':'Expires soon','message':'5-hour 90% left','data':{'credit_id':'c1'}}
    def test_env_secret_resolution(self):
        from codex_reset_guardian.notifications import resolve_value
        os.environ['GUARDIAN_TEST_SECRET']='abc'
        self.assertEqual(resolve_value('env:GUARDIAN_TEST_SECRET'),'abc')
        with self.assertRaises(ValueError): resolve_value('env:DOES_NOT_EXIST_GUARDIAN')
    def test_ntfy_payload_and_bearer_header(self):
        from codex_reset_guardian.notifications import NtfyNotifier
        seen=[]
        def opener(req,timeout=10): seen.append(req); return Response()
        NtfyNotifier('https://ntfy.example/topic','token',opener).send(self.event)
        self.assertEqual(seen[0].full_url,'https://ntfy.example/topic')
        self.assertEqual(seen[0].get_header('Authorization'),'Bearer token')
        self.assertEqual(seen[0].get_header('Title'),'Expires soon')
        self.assertEqual(seen[0].data,b'5-hour 90% left')
    def test_discord_and_telegram_payloads(self):
        from codex_reset_guardian.notifications import DiscordNotifier, TelegramNotifier
        seen=[]
        def opener(req,timeout=10): seen.append(req); return Response()
        DiscordNotifier('https://discord.example/hook',opener).send(self.event)
        TelegramNotifier('bot123','42',opener,base_url='https://tg.example').send(self.event)
        discord=json.loads(seen[0].data); telegram=json.loads(seen[1].data)
        self.assertIn('Expires soon',discord['content'])
        self.assertEqual(telegram['chat_id'],'42'); self.assertIn('5-hour 90% left',telegram['text'])
        self.assertEqual(seen[1].full_url,'https://tg.example/botbot123/sendMessage')
    def test_gotify_and_generic_webhook_payloads(self):
        from codex_reset_guardian.notifications import GotifyNotifier, WebhookNotifier
        seen=[]
        def opener(req,timeout=10): seen.append(req); return Response()
        GotifyNotifier('https://gotify.example','tok',opener).send(self.event)
        WebhookNotifier('https://hooks.example/reset',{'X-Key':'k'},opener).send(self.event)
        self.assertEqual(seen[0].full_url,'https://gotify.example/message?token=tok')
        self.assertEqual(json.loads(seen[0].data)['title'],'Expires soon')
        self.assertEqual(json.loads(seen[1].data)['data']['credit_id'],'c1')
        self.assertEqual(seen[1].get_header('X-key'),'k')
    def test_manager_isolates_backend_failure(self):
        from codex_reset_guardian.notifications import NotificationManager
        class Bad:
            name='bad'
            def send(self,event): raise RuntimeError('offline')
        class Good:
            name='good'
            def __init__(self): self.called=False
            def send(self,event): self.called=True
        good=Good(); result=NotificationManager([Bad(),good]).send(self.event)
        self.assertTrue(good.called)
        self.assertEqual(result,[('bad',False,'offline'),('good',True,None)])

class DesktopNotificationTests(unittest.TestCase):
    def test_desktop_adapter_uses_sync_api_without_callback_loop(self):
        import sys, types
        from codex_reset_guardian.notifications import DesktopNotifier
        calls=[]
        fake=types.ModuleType('desktop_notifier')
        class Urgency:
            Critical='critical'; Normal='normal'
        class Backend:
            def __init__(self,app_name): calls.append(('init',app_name))
            def send(self,**kwargs): calls.append(('send',kwargs)); return 'id'
        fake.DesktopNotifierSync=Backend; fake.Urgency=Urgency
        old=sys.modules.get('desktop_notifier'); sys.modules['desktop_notifier']=fake
        try:
            DesktopNotifier().send({'severity':'warning','title':'Soon','message':'Use Codex','data':{}})
        finally:
            if old is None: sys.modules.pop('desktop_notifier',None)
            else: sys.modules['desktop_notifier']=old
        self.assertEqual(calls[0],('init','Codex Reset Guardian'))
        self.assertEqual(calls[1][1]['title'],'Soon')
        self.assertEqual(calls[1][1]['message'],'Use Codex')
