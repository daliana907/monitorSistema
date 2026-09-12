# Monitor del Sistema, explicado en cristiano

Esto es para cualquiera que quiera saber qué hace este complemento antes de
instalarlo, sin necesidad de saber programar.

## ¿Para qué sirve?

Dice en voz alta cómo está tu equipo: cuánto trabaja el procesador, cuánta
memoria queda, cuánto espacio hay en los discos, cómo va la tarjeta gráfica, la
batería, el Wi-Fi y los aparatos Bluetooth conectados.

Además puede avisarte solo cuando algo se sale de lo normal: que la batería está
baja, que el procesador se calentó, que un disco se está desgastando. Tú decides
qué avisos quieres y a partir de qué valor.

## ¿De dónde saca la información?

Del propio equipo. Le pregunta a Windows lo mismo que podrías preguntarle tú si
abrieras el administrador de tareas, solo que te lo dice hablando.

Para saber el modelo del procesador mira el registro de Windows, **solo para
leer**; el complemento no escribe nunca en el registro. Para las temperaturas y
el Bluetooth usa bibliotecas del propio Windows y del fabricante de tu tarjeta
gráfica, las que ya están instaladas en tu equipo. No trae ningún programa
propio.

## ¿Pide permisos de administrador?

Una sola vez, y solo si tú lo pides: cuando usas el atajo que da el **informe
completo de salud de los discos**.

El motivo es que Windows solo le cuenta a un programa con permisos cuál es la
temperatura de un disco y cuánta vida útil le queda. Sin permisos devuelve esos
campos vacíos.

Lo importante: **la vigilancia automática, la que corre sola en segundo plano,
nunca pide permisos**. Se conforma con menos datos precisamente para no
molestarte con un aviso que tú no pediste. Eso está hecho a propósito.

Si cancelas el aviso, el complemento te lo dice y sigue funcionando con
normalidad.

## ¿Se conecta a internet?

Solo si tú se lo pides, con el atajo de la **prueba de velocidad**. Y te avisa
por voz de que la está haciendo.

Al arrancar no se conecta. En segundo plano no se conecta. No busca
actualizaciones ni manda estadísticas de nada.

Cuando haces la prueba de velocidad contacta con tres sitios: hace un ping a un
servidor de Cloudflare para medir el retardo, descarga un archivo de prueba, y
sube un puñado de datos. **Lo que sube son datos inventados al azar en ese
momento**, no archivos ni información tuya. No manda tu nombre, ni tu ubicación,
ni nada que te identifique.

## ¿Guarda algo en mi equipo?

Tus preferencias —qué avisos quieres, a partir de qué valores, cada cuánto— se
guardan en la configuración normal de NVDA, en el mismo sitio donde NVDA guarda
todo lo demás. No crea archivos aparte.

La única excepción es el informe de discos, que se escribe un momento en la
carpeta temporal de Windows y se borra en cuanto se lee.

## ¿Va a poner lento mi equipo?

No debería. Todo lo que tarda se hace en segundo plano, para que NVDA no se
quede callado mientras tanto.

El vigilante despierta cada cinco segundos, mira si toca algún aviso y se vuelve
a dormir. Y recuerda cuándo comprobó cada cosa, así que no repite el mismo aviso
una y otra vez: respeta el intervalo que tú pusiste.

Cuando cierras NVDA, todo eso se detiene y se cierra limpiamente.

## ¿Puedo fiarme de que hace lo que dice?

El código está publicado entero y cualquiera puede leerlo. Tiene 30 pruebas
automáticas que se ejecutan solas cada vez que se sube un cambio.

Y escribe en el registro de NVDA todo lo que va haciendo: qué procesador
detectó, qué temperatura leyó, qué aparatos Bluetooth encontró y cuáles
descartó, y por qué. Si algo va mal, ahí está la explicación.
