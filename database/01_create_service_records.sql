USE [car-voice-db]
GO

/****** Object:  Table [dbo].[ServiceRecords]    Script Date: 20-09-2026 13:15:16 ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[ServiceRecords](
	[service_id] [int] IDENTITY(1,1) NOT NULL,
	[vehicle_id] [int] NOT NULL,
	[due_maintenance_date] [date] NOT NULL,
	[maintenance_type] [varchar](50) NOT NULL,
	[service_status] [varchar](20) NOT NULL,
	[created_at] [datetime2](7) NOT NULL,
PRIMARY KEY CLUSTERED 
(
	[service_id] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO

ALTER TABLE [dbo].[ServiceRecords] ADD  DEFAULT ('DUE') FOR [service_status]
GO

ALTER TABLE [dbo].[ServiceRecords] ADD  DEFAULT (sysutcdatetime()) FOR [created_at]
GO

ALTER TABLE [dbo].[ServiceRecords]  WITH CHECK ADD  CONSTRAINT [FK_ServiceRecords_Vehicles] FOREIGN KEY([vehicle_id])
REFERENCES [dbo].[Vehicles] ([vehicle_id])
GO

ALTER TABLE [dbo].[ServiceRecords] CHECK CONSTRAINT [FK_ServiceRecords_Vehicles]
GO
