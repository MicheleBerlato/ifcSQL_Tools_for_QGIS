-- 2. Crea la Foreign Table basata su una query dinamica
CREATE FOREIGN TABLE public.mssql_identity_card (
    db_guid uuid,          -- MSSQL uniqueidentifier si mappa bene su UUID
    db_name varchar(255)   -- Giusto per conferma visiva
)
SERVER mssql_ifcsql
OPTIONS (
    -- Invece di schema_name e table_name, usiamo 'query'
    query 'SELECT service_broker_guid AS db_guid, ''ifcSQL'' AS db_name FROM sys.databases WHERE name = ''ifcSQL'''
);

-- 3. Assegna i permessi (opzionale, ma consigliato)
ALTER FOREIGN TABLE public.mssql_identity_card OWNER TO postgres;