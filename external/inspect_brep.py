"""Command-line entry point for canonical Gate 2 B-rep inspection."""

from __future__ import annotations

import argparse

from brep_inspection import inspect_step, write_summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    write_summary(inspect_step(args.input, args.model_id), args.output)


if __name__ == "__main__":
    main()
