CREATE FOREIGN TABLE ifcinstance.EntityAttributeListElementOfEntityRef (
"GlobalEntityInstanceId" bigint,
"OrdinalPosition" integer,
"ListDim1Position" integer,
"TypeId" integer,
"Value" bigint
)
SERVER mssql_ifcsql
OPTIONS (
SCHEMA_NAME 'ifcInstance',
TABLE_NAME 'EntityAttributeListElementOfEntityRef'
);
