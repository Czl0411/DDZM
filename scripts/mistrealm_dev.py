"""Loopback-only development server with mock SDK; never part of publish/."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import uvicorn

from dzmm_bot.core.mistrealm_api import mistrealm_router
from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.schema import Base


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=18741)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]/'gamefy/mistrealm/publish'
    with TemporaryDirectory(prefix='mistrealm-dev-') as directory:
        engine=create_engine(f"sqlite:///{directory}/local.db",connect_args={'check_same_thread':False})
        Base.metadata.create_all(engine)
        repository=CoreRepository(sessionmaker(engine,expire_on_commit=False))
        app=FastAPI()
        app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_methods=["GET","POST"],allow_headers=["Authorization","Content-Type"])
        app.include_router(mistrealm_router(repository,lambda:datetime.now(timezone.utc)))
        @app.get('/',response_class=HTMLResponse)
        def index():
            stub="""<script>
const player=new URLSearchParams(location.search).get('player')||'local-a';
window.dzmm={user:{info:async()=>({id:player,name:player==='local-a'?'雾中旅人':'王城来客'})},loading:{progress(){},ready(){},error(){}}};
</script>"""
            return (root/'index.html').read_text().replace('<script type="module"',stub+'<script type="module"')
        @app.get('/classic/',response_class=HTMLResponse)
        def classic_index():
            stub="""<script>
const player=new URLSearchParams(location.search).get('player')||'classic-local-a';
window.dzmm={user:{info:async()=>({id:player,name:player==='classic-local-a'?'雾中旅人':'王城来客'})},loading:{progress(){},ready(){},error(){}}};
</script>"""
            return (root/'classic/index.html').read_text().replace('<script type="module"',stub+'<script type="module"')
        @app.get('/sandbox',response_class=HTMLResponse)
        def sandbox():
            return '<!doctype html><iframe title="Mistrealm sandbox" sandbox="allow-scripts" src="/?player=sandbox-local" style="border:0;width:100vw;height:100vh"></iframe>'
        app.mount('/',StaticFiles(directory=root),name='assets')
        uvicorn.run(app,host='127.0.0.1',port=args.port)


if __name__=='__main__':
    main()
