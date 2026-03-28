import database as db
try:
    client = db._get_client()
    res = client.table("loans").select("*").limit(1).execute()
    print("Loans Table columns:", res.data[0].keys())
except Exception as e:
    print(e)
