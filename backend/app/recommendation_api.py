"""Real-data recommendation API. Legacy mock routes remain separate."""
from contextlib import asynccontextmanager
import os
import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Request, Query, Path
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from recommendation_service.database.connection import create_db_engine
from recommendation_service.database.repository import SnapshotRepository,RepositoryUnavailable,ReleaseNotFound,ReleaseConflict
from recommendation_service.services.ai_recommendation.application import RecommendationApplication,RegionNotFound
from recommendation_service.services.ai_recommendation.api_schemas import SliderRequest,CompareRequest,ExplainRequest,SliderWeights
from recommendation_service.services.ai_recommendation.llm_service import OpenRouterClient

RELEASE_PATTERN=r"^snapshot-[a-f0-9]{16}$"
DISTRICT_PATTERN=r"^[0-9]{5}$"


def _mapped(error):
    if isinstance(error,(RegionNotFound,ReleaseNotFound)):
        return HTTPException(404,detail={"code":"not_found"})
    if isinstance(error,ReleaseConflict):
        return HTTPException(503,detail={"code":"release_integrity_error"})
    if isinstance(error,RepositoryUnavailable):
        return HTTPException(503,detail={"code":"database_unavailable"})
    return HTTPException(422,detail={"code":"invalid_request"})


def _call(operation,*args,**kwargs):
    try:return operation(*args,**kwargs)
    except (RegionNotFound,ReleaseNotFound,ReleaseConflict,RepositoryUnavailable,ValueError) as error:
        raise _mapped(error) from None


def _weights(value):
    try:
        return SliderWeights.model_validate_json(value) if value is not None else SliderWeights.model_validate({d:20 for d in ("economy","energy","comfort","health","safety")})
    except (ValueError,ValidationError):
        raise HTTPException(422,detail={"code":"invalid_weights"}) from None


def create_recommendation_router(application=None,explanation_client=None):
    router=APIRouter(prefix="/api/recommendation",tags=["실제 추천 데이터"])
    def service(request):
        value=application if application is not None else getattr(request.app.state,"recommendation",None)
        if value is None:raise HTTPException(503,detail={"code":"database_not_configured"})
        return value

    @router.get("/status")
    def status(request:Request):
        app=service(request)
        result=_call(app.repository.get_status)
        if result["active_release"] is None:
            raise HTTPException(503,detail={"code":"no_active_release"})
        data=_call(app.repository.load_dataset,result["active_release"]["release_id"])
        return {"database":"ready",**result,"available_domains":data.available_domains,
                "warnings":data.warnings,"is_mock":data.is_mock}

    @router.get("/districts")
    def districts(request:Request,release_id:str|None=Query(None,pattern=RELEASE_PATTERN),weights:str|None=None):
        return _call(service(request).districts,weights=_weights(weights),release_id=release_id)

    @router.get("/regions")
    def regions(request:Request,release_id:str|None=Query(None,pattern=RELEASE_PATTERN),sigungu_code:str|None=Query(None,pattern=DISTRICT_PATTERN)):
        result=_call(service(request).scores,release_id,sigungu_code)
        result["items"]=[{k:row[k] for k in ("region_code","region_name","sigungu_code","sigungu_name","geometry_key")} for row in result["items"]]
        return result

    @router.get("/scores")
    def scores(request:Request,release_id:str|None=Query(None,pattern=RELEASE_PATTERN),sigungu_code:str|None=Query(None,pattern=DISTRICT_PATTERN),weights:str|None=None):
        return _call(service(request).scores,release_id,sigungu_code,_weights(weights))

    @router.get("/regions/{region_code}")
    def region(request:Request,region_code:str=Path(pattern=r"^[0-9]{6}$"),release_id:str|None=Query(None,pattern=RELEASE_PATTERN)):
        return _call(service(request).region,region_code,release_id)

    @router.post("/recommendations")
    def recommend(body:SliderRequest,request:Request):
        return _call(service(request).recommend,body)

    @router.post("/compare")
    def compare(body:CompareRequest,request:Request):
        return _call(service(request).compare,body)

    @router.post("/explanations")
    async def explain(body:ExplainRequest,request:Request):
        client=explanation_client if explanation_client is not None else getattr(request.app.state,"explanation_client",None)
        try:return await service(request).explain(body,client)
        except (RegionNotFound,ReleaseNotFound,ReleaseConflict,RepositoryUnavailable,ValueError) as error:
            raise _mapped(error) from None
    return router


def build_app(legacy_router,repository=None,explanation_client=None):
    @asynccontextmanager
    async def lifespan(app):
        engine=None;http=None
        app.state.recommendation=None
        app.state.explanation_client=explanation_client
        try:
            supplied=repository
            if supplied is None and os.environ.get("RECOMMENDATION_DATABASE_URL"):
                try:
                    engine=create_db_engine(os.environ["RECOMMENDATION_DATABASE_URL"])
                    supplied=SnapshotRepository(engine)
                except ValueError:
                    supplied=None
            if supplied is not None:app.state.recommendation=RecommendationApplication(supplied)
            if explanation_client is None and os.environ.get("OPENROUTER_API_KEY") and os.environ.get("OPENROUTER_MODEL"):
                http=httpx.AsyncClient(trust_env=False,follow_redirects=False)
                try:
                    app.state.explanation_client=OpenRouterClient(api_key=os.environ["OPENROUTER_API_KEY"],
                        model=os.environ["OPENROUTER_MODEL"],http_client=http,max_tokens=4096)
                except ValueError:
                    app.state.explanation_client=None
            yield
        finally:
            if http is not None:await http.aclose()
            if engine is not None:engine.dispose()
    app=FastAPI(title="Seoul Smart Life API",version="0.2.0",lifespan=lifespan)
    app.add_middleware(CORSMiddleware,allow_origins=["http://localhost:5173","http://127.0.0.1:5173"],allow_methods=["*"],allow_headers=["*"])
    app.include_router(legacy_router)
    app.include_router(create_recommendation_router())
    return app
