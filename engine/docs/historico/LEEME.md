# Documentación histórica

Lo que hay aquí **ya no describe el proyecto**. Se conserva porque sigue
siendo cierto para la etiqueta que documenta, y porque explica de dónde viene
lo que hay ahora.

## `Documentacion_Tecnica_BlockCAD_Engine_Paso_1.docx`

Describe el motor de la etiqueta `paso-1`: un editor de ladrillos de sistema.
Para verlo funcionando:

```cmd
git checkout paso-1
```

Casi todo lo que afirma dejó de ser cierto con el giro a Technic de julio de
2026:

- Las alturas iban en unidades de placa; ahora todo se mide en LDU.
- La rotación solo admitía 0, 90, 180 y 270 grados sobre el eje vertical;
  ahora son las 24 orientaciones de un cubo.
- Decía que `geometry.py` no dependía de ningún otro módulo; hoy importa
  `errors`.
- Su hoja de ruta terminaba en una aplicación de escritorio con PySide6.

La documentación vigente está en `engine/Documentacion_Tecnica_BlockCAD.docx`.
