import urllib.request,re
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
for u in ["https://www.serebii.net/card/","https://www.serebii.net/card/english.shtml","https://www.serebii.net/card/japanese.shtml","https://pokeguardian.com/feed/","https://www.pokeguardian.com/feed","https://www.pokemon-card.com/products/","https://www.pokemon-card.com/info/","https://press.pokemon.com/en/Pokemon-Trading-Card-Game","https://www.pokemon.com/us/pokemon-news","https://bulbapedia.bulbagarden.net/wiki/List_of_Pok%C3%A9mon_Trading_Card_Game_expansions","https://www.pokebeach.com/"]:
    try:
        t=urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":UA}),timeout=30).read().decode("utf-8","ignore")
        ds=re.findall(r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+20(?:26|27)|20(?:26|27)年\d{1,2}月\d{1,2}日",t)
        print("OK",u,len(t),len(ds),ds[:6])
    except Exception as e: print("FAIL",u,e)
