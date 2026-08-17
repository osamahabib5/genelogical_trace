import json
import pandas as pd

def convert_to_excel():
    input_file = "sofafea_models_raw.json"
    output_file = "sofafea_models_clean.xlsx"
    
    try:
        with open(input_file, "r") as f:
            data = json.load(f)
        
        cleaned_list = []
        for item in data:
            # Azure returns a nested 'model' object
            m = item.get("model", {})
            
            cleaned_list.append({
                "Model Name": m.get("name"),
                "Version": m.get("version"),
                "Format": m.get("format"),
                "Deployment Type": ", ".join([s.get("name", "") for s in item.get("skus", [])]),
                "Is Default": item.get("isDefaultVersion"),
                "Status": item.get("status")
            })
            
        df = pd.DataFrame(cleaned_list)
        # Sort by Name and Version so the newest are at the top
        df = df.sort_values(by=["Model Name", "Version"], ascending=[True, False])
        
        df.to_excel(output_file, index=False)
        print(f"Done! Cleaned list saved to {output_file}")
        
    except Exception as e:
        print(f"Error converting file: {e}")

if __name__ == "__main__":
    convert_to_excel()