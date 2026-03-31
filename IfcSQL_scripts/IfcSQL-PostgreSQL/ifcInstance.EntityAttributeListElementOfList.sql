CREATE FOREIGN TABLE ifcinstance.EntityAttributeListElementOfList (
"GlobalEntityInstanceId" bigint,
"OrdinalPosition" integer,
"ListDim1Position" integer,
"TypeId" integer
)
SERVER mssql_ifcsql
OPTIONS (
SCHEMA_NAME 'ifcInstance',
TABLE_NAME 'EntityAttributeListElementOfList'
);
