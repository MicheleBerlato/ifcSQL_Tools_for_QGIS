CREATE FOREIGN TABLE ifcinstance.EntityAttributeListElementOfListElementOfEntityRef (
"GlobalEntityInstanceId" bigint,
"OrdinalPosition" integer,
"ListDim1Position" integer,
"ListDim2Position" integer,
"TypeId" integer,
"Value" bigint
)
SERVER mssql_ifcsql
OPTIONS (
SCHEMA_NAME 'ifcInstance',
TABLE_NAME 'EntityAttributeListElementOfListElementOfEntityRef'
);
