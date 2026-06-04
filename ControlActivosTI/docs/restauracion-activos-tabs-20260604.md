# Restauracion de la mejora de pestañas en /activos

Este cambio partio de un arbol de trabajo limpio para estos archivos:

- `apps/activos/views.py`
- `templates/activos/lista.html`
- `apps/activos/tests.py`

Si quieres volver al estado anterior de esta mejora, ejecuta:

```powershell
git restore -- apps/activos/views.py templates/activos/lista.html apps/activos/tests.py
```

Luego verifica el resultado con:

```powershell
git status --short
```
