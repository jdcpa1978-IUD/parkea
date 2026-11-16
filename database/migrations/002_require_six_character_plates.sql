-- Existing short plates are preserved, while new and updated rows must use six characters.
-- Correct any legacy short plates with their actual values before validating this constraint.
BEGIN;

ALTER TABLE vehiculos
    DROP CONSTRAINT IF EXISTS ck_vehiculo_placa_alfanumerica;
ALTER TABLE vehiculos
    ADD CONSTRAINT ck_vehiculo_placa_alfanumerica
    CHECK (placa ~ '^[A-Z0-9]{6}$') NOT VALID;

COMMIT;
