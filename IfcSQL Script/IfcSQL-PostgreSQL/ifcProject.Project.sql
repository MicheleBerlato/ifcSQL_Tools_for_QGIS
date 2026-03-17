CREATE FOREIGN TABLE ifcproject.Project (
"ProjectId" integer,
"ProjectName" text
)

SERVER mssql_ifcsql
OPTIONS (
SCHEMA_NAME 'ifcProject',
TABLE_NAME 'Project'
);
