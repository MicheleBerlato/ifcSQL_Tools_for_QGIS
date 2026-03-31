CREATE FOREIGN TABLE IF NOT EXISTS ifcinstance.entityattributelistelementoflistelementofinteger(
    "GlobalEntityInstanceId" bigint,
    "OrdinalPosition" integer,
    "ListDim1Position" integer,
    "ListDim2Position" integer,
    "TypeId" integer,
    "Value" integer
)
    SERVER mssql_ifcsql
    OPTIONS (schema_name 'ifcInstance', table_name 'EntityAttributeListElementOfListElementOfInteger');