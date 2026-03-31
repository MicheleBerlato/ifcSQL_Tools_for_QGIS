CREATE MATERIALIZED VIEW ifcproject.projectpostgres AS
SELECT 
    "ProjectNumber_MSSQL",
    "ProjectName",
    COUNT(*) as "Entities"
FROM
    ifcgeometry.entitygeometry
GROUP BY
    "ProjectNumber_MSSQL", 
    "ProjectName"
ORDER BY 
	"ProjectNumber_MSSQL";

CREATE UNIQUE INDEX idx_mv_progetti 
ON ifcproject.projectpostgres ("ProjectNumber_MSSQL", "ProjectName");

CREATE OR REPLACE FUNCTION ifcproject._refresh_vista_progetti()
RETURNS TRIGGER AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY ifcproject.projectpostgres;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_aggiorna_progetti
AFTER INSERT OR UPDATE OR DELETE ON ifcgeometry.entitygeometry
FOR EACH STATEMENT
EXECUTE FUNCTION ifcproject._refresh_vista_progetti();
