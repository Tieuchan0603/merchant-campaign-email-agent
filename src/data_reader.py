# data_reader.py
# Purpose: Read campaign data from data/campaign.xlsx and look up merchants.
#
# Design: Object-Oriented (OOP)
#   - We create a class called CampaignDataReader.
#   - A class is like a blueprint: it groups related data and functions together.
#   - This makes it easy to reuse, test, and extend later.

import pandas as pd
from pathlib import Path

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------
# __file__  → the absolute path of THIS file (data_reader.py)
# .parent   → the src/ folder
# .parent   → the project root folder
# / "data" / "campaign.xlsx" → the Excel file
#
# Using pathlib.Path means this works on both Windows and Mac/Linux.
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_DATA_FILE = PROJECT_ROOT / "data" / "campaign.xlsx"


class CampaignDataReader:
    """
    Reads and queries campaign data from an Excel file.

    Usage example:
        reader = CampaignDataReader()
        info = reader.find_merchant("KFC")
        print(info["Campaign Name"])
    """

    def __init__(self, filepath: Path = DEFAULT_DATA_FILE):
        """
        Initialize the reader with a path to the Excel file.

        Args:
            filepath: Path to campaign.xlsx. Defaults to data/campaign.xlsx
                      in the project root.
        """
        self.filepath = Path(filepath)

        # _df will hold the data as a pandas DataFrame (like a table in memory).
        # We use None here and load lazily (only when first needed).
        self._df = None

    # -----------------------------------------------------------------------
    # Public methods
    # -----------------------------------------------------------------------

    def load_data(self) -> pd.DataFrame:
        """
        Load the Excel file into memory as a pandas DataFrame.

        A DataFrame is like a spreadsheet table: rows and columns.
        After calling this, self._df holds all campaign rows.

        Returns:
            pd.DataFrame: The full campaign table.

        Raises:
            FileNotFoundError: If campaign.xlsx does not exist at self.filepath.
        """
        if not self.filepath.exists():
            raise FileNotFoundError(
                f"Cannot find the Excel file at: {self.filepath}\n"
                f"Please make sure data/campaign.xlsx exists in the project root."
            )

        # pd.read_excel() reads the first sheet by default.
        self._df = pd.read_excel(self.filepath)

        # --- Normalize the Merchant column ---
        # "KFC ", " kfc", "KFC" should all be treated as the same merchant.
        # .str.strip() removes leading/trailing spaces.
        self._df["Merchant"] = self._df["Merchant"].str.strip()

        return self._df

    def list_merchants(self) -> list[str]:
        """
        Return a list of all merchant names in the spreadsheet.

        Returns:
            list[str]: e.g. ["KFC", "BreadTalk"]
        """
        self._ensure_loaded()

        # .tolist() converts the pandas Series (column) to a plain Python list.
        return self._df["Merchant"].tolist()

    def find_merchant(self, name: str) -> dict | None:
        """
        Search for a merchant by name (case-insensitive, whitespace-tolerant).

        Args:
            name: Merchant name to search for, e.g. "kfc" or "KFC ".

        Returns:
            dict: All campaign fields for the first matching row, e.g.:
                  {
                    "Quarter": "Q3",
                    "Merchant": "KFC",
                    "Campaign Name": "World Cup 2026",
                    "Timeline": "1/7-31/7",
                    ...
                  }
            None: If no merchant with that name is found.
        """
        self._ensure_loaded()

        # Normalize the search term the same way we normalized the data.
        name_normalized = name.strip().lower()

        # Create a boolean mask: True for rows where Merchant matches.
        # .str.lower() lowercases all values in the column for comparison.
        mask = self._df["Merchant"].str.lower() == name_normalized

        # Filter the DataFrame to only matching rows.
        matched_rows = self._df[mask]

        # If no rows matched, return None.
        if matched_rows.empty:
            return None

        # Take the first matching row and convert it to a Python dict.
        # .iloc[0] = "integer location 0" = first row.
        # .to_dict() = convert pandas Series → Python dict.
        return matched_rows.iloc[0].to_dict()

    def get_campaign_info(self, name: str) -> dict | None:
        """
        Return full campaign info for a merchant. Alias for find_merchant().

        Useful when you want to be explicit that you're fetching campaign data,
        not just checking if a merchant exists.

        Args:
            name: Merchant name.

        Returns:
            dict or None — same as find_merchant().
        """
        return self.find_merchant(name)

    # -----------------------------------------------------------------------
    # Private helper
    # -----------------------------------------------------------------------

    def _ensure_loaded(self):
        """
        Load data from Excel if it hasn't been loaded yet.

        This is called at the start of every public method that needs data.
        It means you don't have to call load_data() manually before using
        the other methods — it happens automatically.
        """
        if self._df is None:
            self.load_data()


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------
# These exist so that the test file (tests/test_data_reader.py) can import
# find_merchant directly without needing to instantiate the class.
#
# Example in tests:
#   from src.data_reader import find_merchant
#   result = find_merchant("KFC")
#
# Internally, they reuse a single shared instance of CampaignDataReader,
# so the Excel file is only read once during the program's lifetime.
# ---------------------------------------------------------------------------

# Shared instance — created once, reused by all module-level functions.
_default_reader = CampaignDataReader()


def find_merchant(name: str) -> dict | None:
    """Module-level shortcut for CampaignDataReader().find_merchant(name)."""
    return _default_reader.find_merchant(name)


def list_merchants() -> list[str]:
    """Module-level shortcut for CampaignDataReader().list_merchants()."""
    return _default_reader.list_merchants()


def get_campaign_info(name: str) -> dict | None:
    """Module-level shortcut for CampaignDataReader().get_campaign_info(name)."""
    return _default_reader.get_campaign_info(name)
