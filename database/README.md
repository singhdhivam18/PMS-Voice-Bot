# PMS Voice Bot Database Scripts

This folder contains the SQL scripts used by the PMS Voice Bot project.

## `01_create_service_records.sql`

Creates the `dbo.ServiceRecords` table in the `car-voice-db` database, including:

- `service_id` identity primary key
- `vehicle_id` foreign key to `dbo.Vehicles`
- maintenance due date
- maintenance type
- service status with default `DUE`
- `created_at` with UTC timestamp default

## Execution

Run the script against the SQL Server database:

```text
car-voice-db
```

The referenced `dbo.Vehicles` table must already exist because `ServiceRecords.vehicle_id` has a foreign-key constraint to it.
