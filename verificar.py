import sys
sys.path.insert(0, '.')
from app import app

with app.test_client() as c:
    c.post('/login', data={'email':'admin@derechos.on','clave':'Admin#Derechos2026!'})
    r = c.get('/admin/contrato')
    html = r.get_data(as_text=True)

checks = [
    ('Subida', 'Subir plantilla Word'),
    ('Formulario multipart', 'enctype="multipart/form-data"'),
    ('Firma', 'Firma autorizada'),
    ('IA', 'Apoyo juridico con IA'),
    ('Vista previa', 'Ver vista previa'),
    ('Aplicar', 'Aplicar a los'),
    ('Restaurar', 'Restaurar plantilla por defecto'),
]

print("Verificaciones:")
for name, text in checks:
    found = text in html
    print(f"  {name}: {'OK' if found else 'FAIL'}")

has_editor = 'contenteditable' in html
print(f"  Editor eliminado: {'OK' if not has_editor else 'FAIL'}")