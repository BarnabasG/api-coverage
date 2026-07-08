import pytest

pytest_plugins = ["pytester"]


def test_django_discovery(pytester):
    """Test that Django endpoints are discovered and covered."""

    # Create urls.py
    pytester.makepyfile(
        urls="""
        from django.http import JsonResponse
        from django.urls import path

        def root_view(request):
            return JsonResponse({"message": "Hello Django"})

        urlpatterns = [
            path("api/root/", root_view),
        ]
    """
    )

    # Create a conftest.py that defines the app fixture
    pytester.makeconftest("""
        import pytest
        from django.conf import settings
        from django.core.handlers.wsgi import WSGIHandler

        if not settings.configured:
            settings.configure(
                DEBUG=True,
                SECRET_KEY="secret",
                ROOT_URLCONF="urls",
                ALLOWED_HOSTS=["*"],
                INSTALLED_APPS=[],
            )
            import django
            django.setup()

        @pytest.fixture
        def app():
            return WSGIHandler()
    """)

    # Create a test file
    pytester.makepyfile("""
        def test_root(coverage_client):
            response = coverage_client.get("/api/root/")
            assert response.status_code == 200
    """)

    # Run pytest with api-coverage enabled
    result = pytester.runpytest("--api-cov-report", "--api-cov-show-covered-endpoints", "-vv")

    # Check output
    print(result.stdout.str())
    assert "API Coverage Report" in result.stdout.str()
    assert "Covered Endpoints:" in result.stdout.str()
    assert "GET    /api/root/" in result.stdout.str()
    assert "Total API Coverage: 20.0%" in result.stdout.str()
    assert result.ret == 0


def test_django_cbv_methods_and_re_path_templates(pytester):
    """CBVs only count implemented methods; re_path routes become matchable templates."""
    pytester.makepyfile(
        urls="""
        from django.http import JsonResponse
        from django.urls import path, re_path
        from django.views import View

        class GetOnlyView(View):
            def get(self, request):
                return JsonResponse({"ok": True})

        def year_view(request, year):
            return JsonResponse({"year": year})

        urlpatterns = [
            path("only-get/", GetOnlyView.as_view()),
            re_path(r"^articles/(?P<year>[0-9]{4})/$", year_view),
        ]
    """
    )

    pytester.makeconftest("""
        import pytest
        from django.conf import settings
        from django.core.handlers.wsgi import WSGIHandler

        if not settings.configured:
            settings.configure(
                DEBUG=True,
                SECRET_KEY="secret",
                ROOT_URLCONF="urls",
                ALLOWED_HOSTS=["*"],
                INSTALLED_APPS=[],
            )
            import django
            django.setup()

        @pytest.fixture
        def app():
            return WSGIHandler()
    """)

    pytester.makepyfile("""
        def test_articles(coverage_client):
            response = coverage_client.get("/articles/2024/")
            assert response.status_code == 200
    """)

    result = pytester.runpytest("--api-cov-report", "--api-cov-show-covered-endpoints", "-vv")
    output = result.stdout.str()

    assert "GET    /articles/<year>/" in output
    assert "GET    /only-get/" in output
    # CBVs only count implemented handlers; FBVs keep the 5-method default.
    assert "POST   /only-get/" not in output
    assert "POST   /articles/<year>/" in output
    assert "Total API Coverage: 16.67%" in output
    assert result.ret == 0
