from pathlib import Path
import tempfile,tracemalloc,resource,gc
from hi10_downloader.web import Application
with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);app=Application(root/'config',root/'output',password='test')
    app.items=[{'id':str(i),'project_id':str(i//1000),'project':f'Project {i//1000}','filename':str(i)+'.mkv','status':'failed' if i%3 else 'complete','bytes':0} for i in range(50000)]
    tracemalloc.start()
    for i in range(200):
        state=app.snapshot(grouped=True,download_page=i%10)
        group=state['download_groups'][0]
        state=app.snapshot(grouped=True,download_page=i%10,group_pages={group['id']:i%20})
    gc.collect()
    print('cache entries',len(app._queue_groups_cache),'memory',tracemalloc.get_traced_memory(),'rss',resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    for stat in tracemalloc.take_snapshot().statistics('lineno')[:8]:print(stat)
