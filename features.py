from pyramid.view import view_config
from pyramid.response import Response
import lander

@view_config(route_name='features_page', route_pattern='/features')
def features_view(request):
    return Response(lander.LANDER_HTML, content_type='text/html')
