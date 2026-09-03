from ux_final import schema,service,ui_audit
schema.initialize()
assert 'inbox' in service.ACTIONS
hits=ui_audit.run()
print('UX FINAL SELFTEST: OK')
print('UI audit suspicious hits:',len(hits))
