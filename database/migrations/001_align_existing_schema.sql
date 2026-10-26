-- Run once against the existing PARKEA database after taking a backup.
-- Existing naive timestamps are interpreted as America/Bogota local time.
BEGIN;

ALTER TABLE vehiculos
    ALTER COLUMN placa TYPE VARCHAR(6);
ALTER TABLE vehiculos
    ADD CONSTRAINT ck_vehiculo_placa_alfanumerica
    CHECK (placa ~ '^[A-Z0-9]{1,6}$');

ALTER TABLE celdas
    ALTER COLUMN estado SET NOT NULL;

ALTER TABLE registros_acceso
    ALTER COLUMN estado_registro SET NOT NULL,
    ALTER COLUMN fecha_hora_ingreso DROP DEFAULT,
    ALTER COLUMN fecha_hora_salida DROP DEFAULT;
ALTER TABLE registros_acceso
    ALTER COLUMN fecha_hora_ingreso TYPE TIMESTAMPTZ
        USING fecha_hora_ingreso AT TIME ZONE 'America/Bogota',
    ALTER COLUMN fecha_hora_salida TYPE TIMESTAMPTZ
        USING fecha_hora_salida AT TIME ZONE 'America/Bogota';
ALTER TABLE registros_acceso
    ALTER COLUMN fecha_hora_ingreso SET DEFAULT CURRENT_TIMESTAMP,
    ADD CONSTRAINT ck_registro_estado_salida CHECK (
        (estado_registro = 'INGRESO_ACTIVO' AND fecha_hora_salida IS NULL)
        OR (estado_registro = 'FINALIZADO' AND fecha_hora_salida IS NOT NULL)
    );

ALTER TABLE pagos_mensualidad
    ALTER COLUMN fecha_pago DROP DEFAULT;
ALTER TABLE pagos_mensualidad
    ALTER COLUMN fecha_pago TYPE TIMESTAMPTZ
        USING fecha_pago AT TIME ZONE 'America/Bogota';
ALTER TABLE pagos_mensualidad
    ALTER COLUMN fecha_pago SET DEFAULT CURRENT_TIMESTAMP,
    ADD CONSTRAINT ck_pago_monto_positivo CHECK (monto > 0),
    ADD CONSTRAINT ck_pago_rango_fechas
        CHECK (fecha_fin_vencimiento >= fecha_inicio_vencimiento);
CREATE INDEX ix_pagos_usuario_vigencia
    ON pagos_mensualidad(id_usuario, fecha_inicio_vencimiento, fecha_fin_vencimiento);

ALTER TABLE novedades
    ALTER COLUMN fecha_hora DROP DEFAULT;
ALTER TABLE novedades
    ALTER COLUMN fecha_hora TYPE TIMESTAMPTZ
        USING fecha_hora AT TIME ZONE 'America/Bogota';
ALTER TABLE novedades
    ALTER COLUMN fecha_hora SET DEFAULT CURRENT_TIMESTAMP,
    ADD CONSTRAINT ck_novedad_descripcion
        CHECK (length(trim(descripcion)) > 0);

ALTER TABLE vehiculos DROP CONSTRAINT fk_usuario_vehiculo;
ALTER TABLE vehiculos
    ADD CONSTRAINT fk_usuario_vehiculo
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario) ON DELETE RESTRICT;

CREATE UNIQUE INDEX uq_registro_celda_activa
    ON registros_acceso(id_celda) WHERE estado_registro = 'INGRESO_ACTIVO';
CREATE UNIQUE INDEX uq_registro_vehiculo_activo
    ON registros_acceso(id_vehiculo) WHERE estado_registro = 'INGRESO_ACTIVO';

COMMIT;
