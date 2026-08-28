"""项目入口 (TECHNICAL_SOLUTION.md 第 58 章).

配置驱动 (无 argparse): 所有运行期参数均来自 configs/*.yaml 与环境变量.

启动指南:
    # 默认全量运行 (configs/default.yaml)
    python -m src.main

    # 小规模调试 (前 5 题, 输出 submission_smoke.xlsx)
    CONFIG=configs/smoke.yaml python -m src.main

    # 提交前校验已有 submission
    CONFIG=configs/validate.yaml python -m src.main

    # 从 JSONL 结果日志恢复已完成的答案到 submission.xlsx (不调用模型)
    RUN_MODE=recover python -m src.main

    # 从 data/debug/<id>/final_answer.json 恢复答案到 submission.xlsx (不调用模型)
    RUN_MODE=recover_debug python -m src.main

    # 一次性覆盖个别参数 (任意场景 yaml 基础上)
    LIMIT=20 OUTPUT=data/output/x.xlsx python -m src.main
    SUBMISSION=data/output/other.xlsx CONFIG=configs/validate.yaml python -m src.main
"""

from __future__ import annotations

import sys

from src.config.settings import Settings, get_settings
from src.io.question_loader import load_questions
from src.io.submission_writer import preflight_submission
from src.observability.logger import get_logger
from src.observability.metrics import get_metrics
from src.pipeline.runner import Orchestrator

logger = get_logger("main")


def cmd_run(settings: Settings) -> int:
    """执行完整 pipeline: tests.xlsx -> submission.xlsx."""
    tests_path = settings.resolve_path(settings.data.tests)
    files_dir = settings.resolve_path(settings.data.files)
    output_path = settings.resolve_path(settings.data.output)

    logger.info("loading questions from %s", tests_path)
    load_result = load_questions(tests_path, files_dir)
    logger.info(
        "loaded %d valid + %d invalid questions",
        len(load_result.questions),
        len(load_result.invalid_rows),
    )

    if settings.run.limit and settings.run.limit > 0:
        load_result.questions = load_result.questions[: settings.run.limit]
        logger.info("limit applied: processing first %d questions", settings.run.limit)

    orchestrator = Orchestrator(
        tests_path=tests_path,
        files_dir=files_dir,
        output_path=output_path,
        max_workers=settings.concurrency.max_workers,
        save_intermediate=settings.pipeline.save_intermediate,
        dpi=settings.pipeline.pdf_dpi,
    )
    out_path = orchestrator.run(load_result)

    # 最终 preflight 汇总.
    ok, issues = preflight_submission(load_result.all_ids(), out_path)
    if ok:
        logger.info("DONE: submission OK -> %s", out_path)
        return 0
    logger.error("DONE but preflight failed: %s", issues)
    return 1


def cmd_recover(settings: Settings) -> int:
    """从结果日志 (data.journal) 恢复已完成答案并写出 submission.xlsx."""
    tests_path = settings.resolve_path(settings.data.tests)
    files_dir = settings.resolve_path(settings.data.files)
    output_path = settings.resolve_path(settings.data.output)

    logger.info("recovering results from journal to %s", output_path)
    load_result = load_questions(tests_path, files_dir)

    orchestrator = Orchestrator(
        tests_path=tests_path,
        files_dir=files_dir,
        output_path=output_path,
    )
    out_path = orchestrator.recover(load_result)

    # 最终 preflight 汇总.
    ok, issues = preflight_submission(load_result.all_ids(), out_path)
    if ok:
        logger.info("DONE: recovery OK -> %s", out_path)
        return 0
    logger.error("recovery finished but preflight failed: %s", issues)
    return 1


def cmd_recover_debug(settings: Settings) -> int:
    """从 data/debug/<id>/final_answer.json 恢复答案到 submission.xlsx."""
    tests_path = settings.resolve_path(settings.data.tests)
    files_dir = settings.resolve_path(settings.data.files)
    output_path = settings.resolve_path(settings.data.output)

    logger.info("recovering results from debug dir to %s", output_path)
    load_result = load_questions(tests_path, files_dir)

    orchestrator = Orchestrator(
        tests_path=tests_path,
        files_dir=files_dir,
        output_path=output_path,
    )
    out_path = orchestrator.recover_debug(load_result)

    # 最终 preflight 汇总.
    ok, issues = preflight_submission(load_result.all_ids(), out_path)
    if ok:
        logger.info("DONE: recovery OK -> %s", out_path)
        return 0
    logger.error("recovery finished but preflight failed: %s", issues)
    return 1


def cmd_validate(settings: Settings) -> int:
    """只对已有 submission 执行 preflight 检查."""
    tests_path = settings.resolve_path(settings.data.tests)
    submission_rel = settings.run.submission or settings.data.output
    submission_path = settings.resolve_path(submission_rel)
    if not submission_path.exists():
        logger.error("submission not found: %s", submission_path)
        return 2

    # 从 tests.xlsx 读取 id 列表 (不校验 file_name 存在性).
    load_result = load_questions(tests_path, files_dir=None)
    expected_ids = load_result.all_ids()

    ok, issues = preflight_submission(expected_ids, submission_path)
    if ok:
        logger.info("preflight OK: %s (%d ids)", submission_path, len(expected_ids))
        return 0
    logger.error("preflight FAILED:")
    for issue in issues:
        logger.error("  - %s", issue)
    return 1


def main() -> int:
    """主入口: 基于 yaml + 环境变量的配置驱动分发."""
    settings = get_settings()
    logger.info("config: %s (mode=%s)", settings.config_path, settings.run.mode)
    try:
        if settings.run.mode == "validate":
            return cmd_validate(settings)
        if settings.run.mode == "recover":
            return cmd_recover(settings)
        if settings.run.mode == "recover_debug":
            return cmd_recover_debug(settings)
        return cmd_run(settings)
    finally:
        get_metrics().log_summary()


if __name__ == "__main__":
    sys.exit(main())
