"""啟動平台:python -m bridge_platform [--host 0.0.0.0] [--port 8000]

和直接跑 uvicorn 的差別:

  關閉時最多等 3 秒。事件串流是不會自己結束的長連線,uvicorn 預設會
  一直等它們結束,結果舊的程序關不掉,bot 也一直掛在舊程序上收不到
  新事件。限時之後強制斷線,bot 會自動重連到新的程序。

  固定只有一個 worker。平台的狀態在記憶體裡,多個 worker 會各自看到
  不同的房間。
"""

import argparse

import uvicorn


def main():
    p = argparse.ArgumentParser(prog="python -m bridge_platform", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="127.0.0.1", help="要讓別台電腦連進來就用 0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    args = p.parse_args()
    uvicorn.run("bridge_platform.api:app", host=args.host, port=args.port,
                workers=1, timeout_graceful_shutdown=3)


if __name__ == "__main__":
    main()
