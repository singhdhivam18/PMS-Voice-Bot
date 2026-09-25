-- Master data for dev-voice-db
-- Source: Dev_voice_db2.sql
-- Run after 02_create_schema.sql while connected to dev-voice-db.
--
-- This file intentionally seeds ONLY the requested master tables:
--   1. language
--   2. vehicle
--
-- Driver assignments from the source dump are not seeded here because
-- driver rows were not requested as master data and vehicle.driver_id
-- references public.driver(id). Vehicles therefore start unassigned.

BEGIN;

-- ============================================================
-- LANGUAGE MASTER
-- ============================================================

INSERT INTO public.language (id, name, code)
VALUES
    (1, 'Kannada',    'kn'),
    (2, 'Hindi',      'hi'),
    (3, 'Malayalam',  'ml'),
    (4, 'Telugu',     'te'),
    (5, 'Tamil',      'ta'),
    (6, 'English',    'en')
ON CONFLICT (code) DO UPDATE
SET name = EXCLUDED.name;

SELECT setval(
    pg_get_serial_sequence('public.language', 'id'),
    GREATEST((SELECT COALESCE(MAX(id), 1) FROM public.language), 1),
    true
);

-- ============================================================
-- VEHICLE MASTER
-- ============================================================

INSERT INTO public.vehicle (id, external_id, registration_no, driver_id, is_active)
VALUES
    (2,  'd6172650-d2c7-48df-a9aa-4c0f8cafdef5', 'KA01AB9995', NULL, true),
    (3,  'fd361607-2b8c-403b-ae15-2503f460d779', 'KA01AB9980', NULL, true),
    (7,  '56db61b1-1bc2-4194-80ec-7df0bbb7b8d3', 'KA01AB9981', NULL, true),
    (8,  '52272ec9-ab62-4197-8117-a54fc544772f', 'KA01AB99164', NULL, true),
    (9,  '48e36e3a-9678-4245-8bf5-b5a5ffdce436', 'KA01AB9916', NULL, true),
    (10, '4e84d171-80e8-446c-b579-22b456ba608d', 'KA01AB991', NULL, true),
    (11, 'a7c0486b-bdc0-46e1-a1d7-d3b62d9e08b4', 'KA01AB99', NULL, true)
ON CONFLICT (id) DO UPDATE
SET external_id = EXCLUDED.external_id,
    registration_no = EXCLUDED.registration_no,
    is_active = EXCLUDED.is_active;

SELECT setval(
    pg_get_serial_sequence('public.vehicle', 'id'),
    GREATEST((SELECT COALESCE(MAX(id), 1) FROM public.vehicle), 1),
    true
);

COMMIT;
