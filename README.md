# Domain-Concepts-KG
Domain Concepts Knowledge Graph created by static analysis


Σηκώνω server :
uvicorn api:app    

Server Health :
curl http://127.0.0.1:8000/health

Στέλνω post request για να κανω parse github codebase :
Invoke-RestMethod -Method POST -Uri 'http://127.0.0.1:8000/parse' -ContentType 'application/json' -Body '{"choice":"1","repo_url":"https://github.com/robotics-4-all/intelligent_robot_systems"}'

Invoke-RestMethod -Method POST -Uri 'http://127.0.0.1:8000/parse' -ContentType 'application/json' -Body '{"choice":"3","repo_url":"https://github.com/robotics-4-all/streamsim"}'

Invoke-RestMethod -Method POST -Uri 'http://127.0.0.1:8000/parse' -ContentType 'application/json' -Body '{"choice":"2","repo_url":"https://github.com/clibs/clib/tree/master"}'

Invoke-RestMethod -Method POST -Uri 'http://127.0.0.1:8000/parse' -ContentType 'application/json' -Body '{"choice":"4","repo_url":"https://github.com/PhilJay/MPAndroidChart"}'

Invoke-RestMethod -Method POST -Uri 'http://127.0.0.1:8000/parse' -ContentType 'application/json' -Body '{"choice":"4","repo_url":"https://github.com/iluwatar/java-design-patterns"}'

Invoke-RestMethod -Method POST -Uri 'http://127.0.0.1:8000/parse' -ContentType 'application/json' -Body '{"choice":"5","repo_url":"https://github.com/veertly/app"}'


pip install libcst lxml fastapi pydantic uvicorn neo4j

npm install @babel/parser @babel/traverse

uvicorn api:app



MATCH (n)
OPTIONAL MATCH (n)-[r]-(m)
RETURN DISTINCT n, r, m


MATCH (a)-[r]->(b)
WHERE r.final_weight >= 0.7
  AND NOT a.name =~ "^(FILE|CLASS|REPO|FUNCTION|METHOD|NESTED_CLASS|NESTED_FUNCTION)_ANON_.*"
  AND NOT b.name =~ "^(FILE|CLASS|REPO|FUNCTION|METHOD|NESTED_CLASS|NESTED_FUNCTION)_ANON_.*"
  AND (
      toLower(a.name) CONTAINS "robot" 
      OR toLower(b.name) CONTAINS "robot"
  )
RETURN a, r, b


εννοειται να εχει εγκατασταθει το srcml διοτι αλλιως ΔΕΝ θα τρεξουν οι parsers (c, cpp, java) που το χρησιμοποιουν
