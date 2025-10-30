texts = """
./残局/四大名局/关于四大名局的整理.txt
./残局/中国象棋中局妙手300/ReadMe.txt
./残局/车马专集/平凡的话.txt
./残局/车马专集/跋.txt
./残局/车马专集/序.txt
./比赛对局/越南队访华实录/作者自介.txt
./比赛对局/越南队访华实录/赛事简述.txt
./大师专集/王斌专集/致言.txt
./布局/五六炮对反宫马/关于《五六炮对反宫马》的录入感言.txt
./布局/顺炮全集/顺炮全集总结.txt
./布局/象棋布局陷阱100局/几点说明.txt
./布局/象棋布局疑形攻击/readme.txt
./布局/反宫马专集/夹炮屏风——反宫马布局研究/录入者感想.txt
./布局/反宫马专集/夹炮屏风——反宫马布局研究/原序.txt
./布局/象棋布局基本战术/xc.txt
./布局/中炮/中炮对单提马横车研究/雪若云的信箱与QQ.txt
./布局/中炮/中炮过河车急进中兵对屏风马/前言.txt
./布局/士角炮布局/士角炮布局总结.txt
./全局/林兴荣遗局/Readme.txt
./全局/梅花谱/总结.txt
./全局/崇本堂梅花谱/引言.txt
""".splitlines()
import chardet

for i in texts:
    if not i:
        continue
    det = chardet.detect(open(i, "rb").read())
    if det["encoding"] == "GB2312":
        print(det, i)
        with open(i, "rb") as f:
            content = f.read()
            content = content.decode(det["encoding"], errors="ignore")
            print(content)
        with open(i, "w", encoding="utf8") as f:
            f.write(content)
