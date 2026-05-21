import urllib.request, json
r = urllib.request.urlopen("https://YOUR-APP.railway.app/openapi.json")
routes = json.loads(r.read())
for path in routes["paths"]:
    print(path)
