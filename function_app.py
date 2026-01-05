"""
Azure Functions 엔트리포인트
Timer trigger로 매일/반일마다 실행
"""
import azure.functions as func
import asyncio
import logging

from src.main import run_observer

app = func.FunctionApp()


@app.timer_trigger(
    schedule="0 0 9,18 * * *",  # 매일 9시, 18시 실행 (UTC 기준으로 조정 필요)
    arg_name="timer",
    run_on_startup=False,
)
async def rndo_observer(timer: func.TimerRequest) -> None:
    """
    rndo 공고 감시 타이머 함수

    스케줄: 0 0 9,18 * * *
    - 매일 9시, 18시에 실행 (KST 기준으로 하려면 0,9로 변경)
    """
    logging.info("rndo observer 시작")

    try:
        await run_observer()
        logging.info("rndo observer 완료")
    except Exception as e:
        logging.error(f"rndo observer 오류: {e}")
        raise


@app.route(route="trigger", methods=["POST"])
async def manual_trigger(req: func.HttpRequest) -> func.HttpResponse:
    """수동 실행용 HTTP 트리거"""
    logging.info("수동 트리거 실행")

    try:
        await run_observer()
        return func.HttpResponse("rndo 실행 완료", status_code=200)
    except Exception as e:
        logging.error(f"오류: {e}")
        return func.HttpResponse(f"오류: {e}", status_code=500)
