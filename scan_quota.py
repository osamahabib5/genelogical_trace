import subprocess
import json
import pandas as pd
import os

# Set this to 1 to prevent Git Bash from mangling paths if you run it there
os.environ["MSYS_NO_PATHCONV"] = "1"

def get_azure_usage(region):
    """
    Scans a specific Azure region for ALL Cognitive Services usage/quota.
    """
    print(f"Scanning region: {region}...")
    cmd = [
        "az", "cognitiveservices", "usage", "list", 
        "--location", region, 
        "--output", "json"
    ]
    
    try:
        # shell=True is necessary on Windows to find 'az' in the PATH
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, shell=True)
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"  [!] Error scanning {region}: {e.stderr.strip()}")
        return []
    except Exception as e:
        print(f"  [!] Unexpected error in {region}: {e}")
        return []

def main():
    # Complete list of regions to scan
    regions = [
        "eastus", 
        "eastus2", 
        "swedencentral", 
        "westus3", 
        "australiaeast", 
        "francecentral",
        "uksouth",
        "japaneast",
        "canadacentral"
    ]
    
    all_data = []

    for region in regions:
        usage_data = get_azure_usage(region)
        
        if not usage_data:
            continue

        for item in usage_data:
            name_info = item.get("name", {})
            model_display_name = name_info.get("localizedValue", "Unknown Model")
            raw_name = name_info.get("value", "")
            
            limit = item.get("limit", 0)
            current = item.get("currentValue", 0)
            
            # Determine Availability Status
            status = "AVAILABLE" if limit > 0 else "NOT AVAILABLE"
            
            all_data.append({
                "Region": region,
                "Status": status,
                "Model Name": model_display_name,
                "Internal Name": raw_name,
                "Quota Limit": limit,
                "Currently Used": current,
                "Unit": item.get("unit")
            })

    if all_data:
        df = pd.DataFrame(all_data)
        
        # Sort by Status and Region for better readability
        df = df.sort_values(by=["Status", "Region", "Model Name"])
        
        output_file = "full_azure_model_inventory.xlsx"
        df.to_excel(output_file, index=False)
        
        print(f"\nScan Complete! Full inventory saved to {output_file}")
        
        # Print a quick summary of what IS available
        print("\n--- Available Models Summary ---")
        available_only = df[df["Status"] == "AVAILABLE"]
        if not available_only.empty:
            print(available_only[["Region", "Model Name", "Quota Limit"]].to_string(index=False))
        else:
            print("No models with active quota found.")
    else:
        print("\nNo data retrieved. Verify your Azure CLI login status (az login).")

if __name__ == "__main__":
    main()