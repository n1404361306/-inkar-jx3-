# Vendored from jx3bla/tools/LoadData.py (LuaTableAnalyserToDict)


class LuaTableAnalyserToDict:
    def parseLuatable(self, n, maxn):
        nowi = n
        nowDict = {}
        nowKey = ""
        nowItem = ""
        nowLabel = 1
        keyStart = 0
        keyQuote = 0
        keyDash = 0

        while True:
            c = self.s[nowi]
            if c == "[" and keyQuote != 1:
                keyStart = 1
            elif c == "{" and keyQuote != 1:
                jdata, pn = self.parseLuatable(nowi + 1, maxn)
                nowi = pn
                nowItem = jdata
            elif keyStart == 1:
                if c == "]":
                    keyStart = 0
                else:
                    nowKey += c
            elif keyStart == 0:
                if c == "\\":
                    keyDash = 1
                if c == '"' and not keyDash:
                    keyQuote = (keyQuote + 1) % 2
                if c != "\\":
                    keyDash = 0
                if c == "," and keyQuote != 1:
                    if nowKey != "":
                        nowDict[nowKey] = nowItem
                    else:
                        nowDict[str(nowLabel)] = nowItem
                    nowItem = ""
                    nowKey = ""
                    nowLabel += 1
                elif c == "}":
                    if nowItem != "":
                        if nowKey != "":
                            nowDict[nowKey] = nowItem
                        else:
                            nowDict[str(nowLabel)] = nowItem
                    return nowDict, nowi
                elif c != "=":
                    nowItem += c
            nowi += 1
            if nowi >= maxn:
                break
        return nowDict, nowi

    def analyse(self, s, delta=8):
        self.s = s
        res, _ = self.parseLuatable(delta, len(self.s))
        self.s = ""
        return res
