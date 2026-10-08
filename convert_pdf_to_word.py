from pathlib import Path

from pdf2docx import Converter

INPUT_PDF = "omer-habib-Business-Analyst.pdf"


def convert_pdf_to_word(input_pdf: str, output_docx: str | None = None) -> None:
    """Convert a PDF file into a Word (.docx) document."""
    pdf_path = Path(input_pdf)
    if not pdf_path.exists():
        raise FileNotFoundError(f"Input file not found: {pdf_path.resolve()}")

    output_docx = output_docx or str(pdf_path.with_suffix(".docx"))

    print(f"Converting '{pdf_path.name}' -> '{Path(output_docx).name}' ...")
    cv = Converter(str(pdf_path))
    cv.convert(output_docx)
    cv.close()
    print(f"Done! Word document saved to: {Path(output_docx).resolve()}")


if __name__ == "__main__":
    import sys

    input_file = sys.argv[1] if len(sys.argv) > 1 else INPUT_PDF
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    convert_pdf_to_word(input_file, output_file)
