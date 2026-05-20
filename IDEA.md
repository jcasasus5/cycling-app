# Idea completa de la app para Tacx FLUX 2 Smart

La idea es crear una aplicación local para ordenador que permita entrenar con un rodillo inteligente Tacx® FLUX 2 Smart simulando puertos reales a partir de perfiles de altimetría. La app estaría pensada para sustituir el uso de aplicaciones externas de pago, ofreciendo una experiencia personalizada, sencilla y centrada en una función principal: cargar o crear rutas de subida, controlar automáticamente la dureza del rodillo según la pendiente y guardar todo el entrenamiento realizado.

La aplicación funcionaría en local, instalada en el ordenador del usuario, y se conectaría directamente al rodillo Tacx FLUX 2 Smart mediante Bluetooth o ANT+ FE-C. El objetivo es que el rodillo reciba instrucciones de pendiente o resistencia durante el entrenamiento para que la sensación sobre la bici cambie según el punto de la ruta en el que se encuentre el usuario. Si la ruta entra en una subida dura, la app aumentaría la resistencia; si llega un tramo más suave o una pendiente negativa, la resistencia se reduciría.

## Concepto general

La app permitiría crear una biblioteca personal de puertos, subidas y rutas virtuales. Cada ruta estaría compuesta por datos estructurados: nombre, distancia total, desnivel acumulado, altitud inicial, altitud final, pendiente media, pendiente máxima, segmentos por kilómetro o por tramo, y configuración de simulación asociada.

Una de las funciones principales sería poder subir una imagen de un perfil de puerto, como una captura de una altimetría. La app enviaría esa imagen a una API de OpenAI con capacidad de visión para extraer los datos relevantes del perfil. A partir de esa imagen, OpenAI devolvería información estructurada en formato JSON: nombre del puerto, distancia, desnivel, altitudes, pendientes por tramo y cualquier otro dato visible o inferible.

La imagen original solo serviría como fuente de datos. Una vez extraídos los datos, la app generaría su propio gráfico de perfil, siempre con el mismo estilo visual. Así, aunque las imágenes originales provengan de webs distintas, tengan diseños diferentes, colores distintos o formatos irregulares, dentro de la aplicación todas las rutas se verían de forma uniforme.

## Importación de rutas desde imagen

El usuario podría subir una imagen de un puerto o perfil de altimetría. La app analizaría la imagen, detectaría los datos visibles y construiría una ruta editable. Después del análisis, la app mostraría una pantalla de revisión con los datos extraídos.

En esa pantalla aparecerían elementos como:

* Nombre de la ruta o puerto.
* Distancia total.
* Desnivel positivo.
* Altitud inicial.
* Altitud final.
* Pendiente media.
* Pendiente máxima.
* Tabla de segmentos con distancia y pendiente.
* Gráfico generado por la propia app.

El usuario podría corregir manualmente cualquier dato antes de guardar la ruta. Esto sería importante porque algunas imágenes pueden tener texto pequeño, datos poco claros, tramos mal alineados o información incompleta. La app no debería depender ciegamente de la extracción automática, sino permitir una revisión rápida antes de guardar.

Una vez revisada, la ruta quedaría guardada en la biblioteca de rutas de la app.

## Gráfico propio de la app

Todas las rutas tendrían un gráfico generado internamente por la aplicación. Este gráfico mostraría el perfil de altitud a lo largo de la distancia, con el eje horizontal representando los kilómetros y el eje vertical representando la altitud. Además, podría mostrar colores o etiquetas según la dureza de la pendiente.

El gráfico podría incluir:

* Línea o área de altitud.
* Colores por tramo según pendiente.
* Etiquetas de porcentaje de pendiente.
* Kilómetros marcados en el eje horizontal.
* Altitud inicial y final.
* Desnivel acumulado.
* Pendiente media y máxima.
* Marcador de posición durante el entrenamiento.

Durante una actividad, el gráfico no sería solo estático. También mostraría en tiempo real por dónde va el usuario. Podría aparecer una línea vertical, un punto o un marcador sobre el perfil indicando el kilómetro actual. El tramo actual podría resaltarse para que el usuario vea claramente qué parte de la subida está realizando.

## Biblioteca de rutas guardadas

La app tendría una sección de rutas guardadas. En esta biblioteca aparecerían todos los puertos o rutas que el usuario haya creado o importado previamente. Cada ruta se mostraría como una tarjeta o elemento de lista con sus datos principales.

Por ejemplo:

**Navacerrada**
13,58 km · 669 m+ · 4,92% media · 10% máx.

Cada ruta guardada permitiría:

* Ver el perfil completo.
* Editar los datos de la ruta.
* Revisar la configuración de simulación.
* Duplicar la ruta.
* Iniciar un entrenamiento.
* Eliminar la ruta.

La biblioteca también podría incluir filtros u opciones de ordenación por nombre, distancia, desnivel, pendiente media, pendiente máxima o fecha de creación.

## Configuración de simulación

Cada ruta se simularía siempre al 100% de su pendiente real. La aplicación no tendría un ajuste para suavizar o aumentar artificialmente la dureza de la ruta. Si un tramo del puerto marca un 8%, la app enviaría un 8% al rodillo. Si marca un 12%, enviaría un 12%.

La única limitación sería la capacidad máxima del Tacx FLUX 2 Smart. Si algún tramo de la ruta supera el máximo que puede simular el rodillo, la app enviaría automáticamente el valor máximo permitido. Por ejemplo, si una rampa aparece al 18% y el límite práctico configurado para el rodillo es 16%, la app mostraría el 18% como pendiente real del puerto, pero enviaría 16% al rodillo.

La configuración podría incluir:

* Pendiente máxima permitida por el rodillo.
* Activación o desactivación de pendientes negativas.
* Suavizado de cambios bruscos de pendiente.
* Peso del ciclista.
* Peso de la bici.
* Modo de simulación realista.

Como el Tacx FLUX 2 Smart puede simular pendientes elevadas, la app estaría preparada para manejar pendientes positivas fuertes, pendientes suaves y pendientes negativas. En las pendientes negativas, el rodillo no empujaría la bici como una bajada real motorizada, pero sí podría reducir la resistencia y permitir que la velocidad virtual aumente.

## Pantalla de entrenamiento en directo

Cuando el usuario empieza una ruta, la app pasaría a una pantalla de entrenamiento en vivo. Esta pantalla mostraría el gráfico del puerto, la posición actual dentro de la ruta y todos los datos relevantes del entrenamiento.

La pantalla principal de entrenamiento incluiría:

* Nombre de la ruta.
* Gráfico del perfil con marcador de posición.
* Kilómetro actual y distancia total.
* Pendiente actual.
* Pendiente del siguiente tramo.
* Tiempo activo.
* Tiempo total.
* Velocidad actual.
* Velocidad media.
* Cadencia actual.
* Cadencia media.
* Potencia actual.
* Potencia media.
* Altitud virtual actual.
* Desnivel virtual acumulado.
* Estado de la actividad: en marcha, pausada o finalizada.

La app recibiría datos del rodillo, como velocidad, cadencia y potencia, y usaría esa información para calcular el avance por la ruta. Según el kilómetro virtual alcanzado, la app consultaría el perfil guardado de la ruta y enviaría al rodillo la pendiente correspondiente.

El comportamiento esperado sería que el usuario sintiera en las piernas los cambios del perfil. Si llega un tramo al 8%, el rodillo se endurece. Si el perfil pasa a un 3%, se suaviza. Si hay una bajada o falso llano descendente, la resistencia baja.

## Autopause y reanudación automática

La aplicación incluiría una función de autopausa. Si el usuario deja de pedalear y la velocidad cae a cero o prácticamente cero durante unos segundos, la actividad se pausaría automáticamente. Esto evitaría que el tiempo activo siguiera contando mientras el usuario está parado.

La app diferenciaría entre:

* Tiempo total transcurrido.
* Tiempo activo real.
* Tiempo pausado.

Cuando la actividad esté pausada, la pantalla mostraría el estado de pausa y ofrecería acciones claras:

* Continuar automáticamente al volver a pedalear.
* Guardar y salir.
* Terminar actividad.
* Descartar actividad.

Cuando el usuario vuelva a pedalear y la velocidad vuelva a superar un umbral mínimo, la app reanudaría automáticamente la actividad. El marcador en el gráfico continuaría desde el mismo punto y el tiempo activo volvería a contar.

## Guardado durante la ruta

La app permitiría guardar una actividad tanto al finalizar la ruta completa como a mitad de recorrido. Si el usuario se detiene, la actividad entra en autopausa y decide no continuar, podría guardar lo realizado hasta ese momento.

Una actividad guardada parcialmente conservaría todos los datos realizados hasta el punto de parada:

* Ruta utilizada.
* Fecha y hora de inicio.
* Fecha y hora de finalización o guardado.
* Estado de la actividad: completada o parcial.
* Distancia recorrida.
* Tiempo activo.
* Tiempo total.
* Velocidad media.
* Cadencia media.
* Potencia media.
* Potencia máxima.
* Desnivel virtual completado.
* Pendientes simuladas.
* Datos segundo a segundo o tramo a tramo.

Así, aunque el usuario solo complete una parte del puerto, la actividad quedaría registrada y disponible para consultarla posteriormente.

## Actividades realizadas

La app tendría una sección específica de actividades hechas. Esta sección funcionaría como un historial personal de entrenamientos. Ahí aparecerían todas las actividades guardadas, tanto completadas como parciales.

Cada actividad podría mostrarse con un resumen como:

**Navacerrada**
20 mayo 2026 · 7,42 km · 28:34 · 228 W media · Parcial

O bien:

**Morcuera**
18,10 km · 1:05:22 · 214 W media · Completada

La sección de actividades permitiría buscar y ordenar por:

* Fecha.
* Ruta.
* Distancia.
* Duración.
* Potencia media.
* Cadencia media.
* Estado de actividad.
* Desnivel realizado.

## Detalle de una actividad guardada

Al entrar en una actividad concreta, la app mostraría un análisis completo de lo realizado. La pantalla combinaría el perfil de la ruta con los datos reales del entrenamiento.

El usuario podría ver:

* Resumen general de la actividad.
* Gráfico del perfil con el tramo completado resaltado.
* Punto final alcanzado si la actividad fue parcial.
* Potencia a lo largo del tiempo o de la distancia.
* Cadencia a lo largo del tiempo o de la distancia.
* Velocidad a lo largo del tiempo o de la distancia.
* Pendiente simulada a lo largo de la ruta.
* Altitud virtual recorrida.
* Pausas realizadas.
* Tiempo activo frente a tiempo total.

El gráfico de actividad permitiría revisar no solo cómo era la ruta, sino cómo la hizo realmente el usuario. Por ejemplo, podría verse que en un tramo al 8% la potencia subió, que en una zona más suave la cadencia aumentó o que hubo una pausa en determinado kilómetro.

## Datos que se guardarían

La app necesitaría guardar dos tipos principales de información: datos de rutas y datos de actividades.

Las rutas serían perfiles teóricos. Contendrían la información del puerto o recorrido antes de entrenar. Las actividades serían sesiones reales realizadas por el usuario sobre una de esas rutas.

Para las rutas se guardarían datos como:

* Identificador de ruta.
* Nombre.
* Imagen original, si existe.
* Fecha de creación.
* Distancia total.
* Altitud inicial.
* Altitud final.
* Desnivel positivo.
* Pendiente media.
* Pendiente máxima.
* Segmentos de la ruta.
* Configuración de simulación.

Para las actividades se guardarían datos como:

* Identificador de actividad.
* Ruta asociada.
* Fecha de inicio.
* Fecha de finalización.
* Estado: completada o parcial.
* Tiempo activo.
* Tiempo total.
* Distancia recorrida.
* Velocidad media.
* Cadencia media.
* Potencia media.
* Potencia máxima.
* Desnivel virtual completado.
* Pausas.
* Muestras de datos registradas durante el entrenamiento.

Cada muestra de actividad podría guardar información como:

* Segundo o marca temporal.
* Kilómetro actual.
* Velocidad.
* Cadencia.
* Potencia.
* Pendiente simulada.
* Altitud virtual.
* Estado de pausa.

Gracias a estas muestras, la app podría reconstruir los gráficos de cualquier actividad guardada.

## Base de datos local

La aplicación necesitaría una base de datos local para guardar rutas, configuraciones y actividades. Para una app que corre en el ordenador del usuario, una base de datos tipo SQLite sería suficiente. Toda la información podría guardarse en un archivo local dentro del propio ordenador.

La base de datos serviría para mantener:

* La biblioteca de rutas.
* Los segmentos de cada ruta.
* Las configuraciones de simulación.
* Las actividades realizadas.
* Las muestras de datos de cada actividad.
* Las imágenes originales importadas.

Esto permitiría usar la aplicación sin depender de una cuenta externa ni de una nube. La única parte que necesitaría internet sería el análisis de imágenes con OpenAI, si se usa esa función.

## Conexión con el Tacx FLUX 2 Smart

La aplicación se conectaría al Tacx FLUX 2 Smart para leer datos y controlar la resistencia. El rodillo enviaría datos como potencia, velocidad y cadencia, y la app le enviaría instrucciones de simulación de pendiente o resistencia.

Durante el entrenamiento, el ciclo sería continuo:

1. La app lee los datos actuales del rodillo.
2. Calcula la distancia virtual recorrida.
3. Determina en qué punto de la ruta está el usuario.
4. Busca la pendiente correspondiente en el perfil.
5. Aplica el límite máximo del rodillo si la pendiente real supera la capacidad permitida.
6. Envía la pendiente o resistencia resultante al rodillo.
7. Actualiza la pantalla y guarda la muestra de actividad.

La app debería incluir indicadores claros de conexión para saber si el rodillo está conectado, si está recibiendo datos y si está aceptando los cambios de resistencia.

## Experiencia visual de la app

La aplicación tendría una interfaz limpia y muy centrada en el entrenamiento. No necesitaría vídeos, avatares ni mundos virtuales. La experiencia se basaría en datos, perfil de altimetría y control real del rodillo.

Las secciones principales serían:

* Importar ruta.
* Biblioteca de rutas.
* Detalle de ruta.
* Entrenamiento en directo.
* Actividades realizadas.
* Detalle de actividad.
* Ajustes de rodillo y simulación.

El estilo visual debería ser consistente, especialmente en los gráficos de perfil. La idea es que cualquier puerto importado acabe teniendo el mismo lenguaje visual dentro de la app, independientemente de cómo fuera la imagen original.

## Funciones principales de la aplicación

La app permitiría:

* Subir una imagen de un perfil de puerto.
* Extraer datos automáticamente usando OpenAI.
* Revisar y editar los datos extraídos.
* Generar un gráfico propio y uniforme de la ruta.
* Guardar rutas en una biblioteca local.
* Simular cada ruta al 100% de su pendiente real, limitando solo los tramos que superen el máximo del rodillo.
* Conectarse al Tacx FLUX 2 Smart.
* Leer velocidad, cadencia y potencia del rodillo.
* Simular pendientes según el punto de la ruta.
* Mostrar el avance sobre el gráfico en tiempo real.
* Mostrar métricas en directo durante el entrenamiento.
* Pausar automáticamente cuando la velocidad cae a cero.
* Reanudar automáticamente cuando el usuario vuelve a pedalear.
* Guardar actividades completadas.
* Guardar actividades parciales.
* Consultar un historial de actividades.
* Abrir una actividad guardada y ver sus gráficos y métricas.

## Idea final

La aplicación sería una herramienta personal para convertir perfiles de puertos reales en entrenamientos interactivos para el Tacx FLUX 2 Smart. El usuario podría coger una imagen de una altimetría, transformarla en una ruta estructurada, guardarla, verla con un gráfico propio y entrenarla sobre el rodillo con cambios automáticos de dureza.

Además, cada entrenamiento quedaría registrado como una actividad real, con sus datos de potencia, cadencia, velocidad, tiempo, distancia, pausas y avance sobre la ruta. La app combinaría tres elementos: extracción inteligente de rutas desde imágenes, simulación física en el rodillo y registro detallado de actividades.

El resultado sería una aplicación local, personalizada y enfocada en subir puertos reales desde casa, sin depender de plataformas externas de entrenamiento ni de suscripciones.
