CREATE FOREIGN TABLE ifcinstance.EntityAttributeListElementOfBinary (
"GlobalEntityInstanceId" bigint,
"OrdinalPosition" integer,
"ListDim1Position" integer,
"TypeId" integer,
"Value" text
)
SERVER mssql_ifcsql
OPTIONS (
SCHEMA_NAME 'ifcInstance',
TABLE_NAME 'EntityAttributeListElementOfBinary'
);
