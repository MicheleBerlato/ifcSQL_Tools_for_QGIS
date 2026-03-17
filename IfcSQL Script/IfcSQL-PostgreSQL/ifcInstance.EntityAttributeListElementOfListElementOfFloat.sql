CREATE FOREIGN TABLE IF NOT EXISTS ifcinstance.entityattributelistelementoflistelementoffloat(
    "GlobalEntityInstanceId" bigint,
    "OrdinalPosition" integer,
    "ListDim1Position" integer,
    "ListDim2Position" integer,
    "TypeId" integer,
    "Value" double precision
)
    SERVER mssql_ifcsql
    OPTIONS (schema_name 'ifcInstance', table_name 'EntityAttributeListElementOfListElementOfFloat');