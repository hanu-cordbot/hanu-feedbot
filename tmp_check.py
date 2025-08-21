import json,sys
try:
    fm=json.load(open('tmp_feed_map.json'))
except Exception as e:
    print('Failed loading tmp_feed_map.json:',e); sys.exit(1)
try:
    data=json.load(open('tmp_feeds.json'))
except Exception as e:
    print('Failed loading tmp_feeds.json:',e); sys.exit(1)
feeds=data.get('feeds',[])
TYPE_EMOJI={'forum':'','voice':'','announcement':'','text':''}
for f in feeds[:50]:
    url=f.get('url')
    m=fm.get(url)
    if isinstance(m, dict):
        chid=m.get('channel')
        name=m.get('channel_name') or (chid and f'Channel-{str(chid)[-4:]}')
        typ=m.get('channel_type') or 'text'
    elif m:
        chid=str(m)
        name=f'Channel-{chid[-4:]}'
        typ='text'
    else:
        chid=None; name='Not mapped'; typ='text'
    emoji=TYPE_EMOJI.get(typ,'')
    print(url,'->',emoji,name)
