"""项目入口 (TECHNICAL_SOLUTION.md 第 58 章).

提供 CLI:
    python -m src.main --tests data/tests.xlsx --files data/files --output data/output/submission.xlsx
    python -m src.main --validate-only --tests data/tests.xlsx --submission data/output/submission.xlsx
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.config.settings import get_settings
from src.io.question_loader import load_questions
from src.io.submission_writer import preflight_submission
from src.observability.logger import get_logger
from src.observability.metrics import get_metrics
from src.pipeline.runner import Orchestrator

logger = get_logger("main")


def _build_arg_parser() -> argparse.ArgumentParser:
    """构造命令行参数解析器."""
    p = argparse.ArgumentParser(description="复杂表格视觉理解与问答系统")
    p.add_argument("--tests", default="data/tests.xlsx", help="tests.xlsx 路径")
    p.add_argument("--files", default="data/files", help="表格文件目录")
    p.add_argument("--output", default="data/output/submission.xlsx", help="submission.xlsx 输出路径")
    p.add_argument("--config", default=None, help="自定义配置文件路径")
    p.add_argument("--max-workers", type=int, default=None, help="最大并发数")
    p.add_argument("--dpi", type=int, default=None, help="PDF 渲染分辨率")
    p.add_argument("--no-intermediate", action="store_true", help="不保存中间产物")
    p.add_argument("--limit", type=int, default=None, help="只处理前 N 道题 (调试用)")
    p.add_argument("--validate-only", action="store_true", help="只对已有 submission 执行 preflight 检查")
    p.add_argument("--submission", default=None, help="待校验的 submission 路径 (配合 --validate-only)")
    return p


def cmd_run(args: argparse.Namespace) -> int:
    """执行完整 pipeline: tests.xlsx -> submission.xlsx."""
    settings = get_settings(args.config)
    tests_path = Path(args.tests)
    files_dir = Path(args.files)
    output_path = Path(args.output)

    logger.info("loading questions from %s", tests_path)
    load_result = load_questions(tests_path, files_dir)
    logger.info("loaded %d valid + %d invalid questions", len(load_result.questions), len(load_result.invalid_rows))

    if args.limit:
        load_result.questions = load_result.questions[: args.limit]
        logger.info("limit applied: processing first %d questions", args.limit)

    orchestrator = Orchestrator(
        tests_path=tests_path,
        files_dir=files_dir,
        output_path=output_path,
        max_workers=args.max_workers,
        save_intermediate=not args.no_intermediate,
        dpi=args.dpi,
    )
    out_path = orchestrator.run(load_result)

    # 最终 preflight 汇总.
    ok, issues = preflight_submission(load_result.all_ids(), out_path)
    if ok:
        logger.info("DONE: submission OK -> %s", out_path)
        return 0
    logger.error("DONE but preflight failed: %s", issues)
    return 1


def cmd_validate(args: argparse.Namespace) -> int:
    """只对已有 submission 执行 preflight 检查."""
    tests_path = Path(args.tests)
    submission_path = Path(args.submission or args.output)
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


def main(argv: list[str] | None = None) -> int:
    """主入口."""
    args = _build_arg_parser().parse_args(argv)
    try:
        if args.validate_only:
            return cmd_validate(args)
        return cmd_run(args)
    finally:
        get_metrics().log_summary()


if __name__ == "__main__":
    sys.exit(main())
