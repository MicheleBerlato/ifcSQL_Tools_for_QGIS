CREATE FOREIGN TABLE ifcinstance.EntityAttributeListElementOfFloat (
"GlobalEntityInstanceId" bigint,
"OrdinalPosition" integer,
"ListDim1Position" integer,
"TypeId" integer,
"Value" double precision
)
SERVER mssql_ifcsql
OPTIONS (
SCHEMA_NAME 'ifcInstance',
TABLE_NAME 'EntityAttributeListElementOfFloat'
);
