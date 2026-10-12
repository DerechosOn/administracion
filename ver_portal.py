import requests
B='http://127.0.0.1:5000'
s=requests.Session()
s.post(B+'/login', data={'email':'ana@test.com','clave':'Test1234'}, timeout=20)
r=s.get(B+'/cliente', timeout=30)
print('Status:', r.status_code)
print('Bytes:', len(r.content))
if 'Hola, Ana' in r.text:
    print('OK Saludo personalizado')
if 'Reclamacion laboral por despido' in r.text:
    print('OK Proceso visible')
if 'En trámite' in r.text:
    print('OK Estado del proceso')
if 'Estado de cuenta' in r.text:
    print('OK Sección Estado de cuenta')
if '5.000.000' in r.text or '5000000' in r.text:
    print('OK Cartera visible')
idx = r.text.find('Hola, Ana')
if idx >= 0:
    print('--- Fragmento ---')
    print(r.text[idx:idx+500])