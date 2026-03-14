from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class GeneratedTest(Base):
    __tablename__ = "generated_tests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    requirement_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    framework: Mapped[str] = mapped_column(String(32), nullable=False)
    requirement_text: Mapped[str] = mapped_column(Text, nullable=False)
    generated_code: Mapped[str] = mapped_column(Text, nullable=False)
    model_used: Mapped[str] = mapped_column(String(64), nullable=False)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    validation_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    output_file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)


class FlakyTestRun(Base):
    __tablename__ = "flaky_test_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    source_file: Mapped[str | None] = mapped_column(String(512), nullable=True)
    total_tests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    flaky_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    results: Mapped[list["FlakyTestResult"]] = relationship(
        "FlakyTestResult", back_populates="run", cascade="all, delete-orphan"
    )


class FlakyTestResult(Base):
    __tablename__ = "flaky_test_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("flaky_test_runs.id"), nullable=False
    )
    test_name: Mapped[str] = mapped_column(String(256), nullable=False)
    fail_rate: Mapped[float] = mapped_column(Float, nullable=False)
    total_runs: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    ai_suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(64), nullable=True)
    suggestion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    run: Mapped["FlakyTestRun"] = relationship("FlakyTestRun", back_populates="results")

    __table_args__ = (Index("ix_flaky_results_test_run", "test_name", "run_id"),)


class HealedSelector(Base):
    __tablename__ = "healed_selectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    healed_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    description: Mapped[str] = mapped_column(String(256), nullable=False)
    old_selector: Mapped[str] = mapped_column(String(512), nullable=False)
    new_selector: Mapped[str] = mapped_column(String(512), nullable=False)
    html_context_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    model_used: Mapped[str] = mapped_column(String(64), nullable=False)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    validation_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    applied_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("ix_healed_old_selector_html", "old_selector", "html_context_hash"),
    )
