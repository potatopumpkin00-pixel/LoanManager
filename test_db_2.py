import database as db
try:
    client = db._get_client()
    res = client.table("loans").select("*").limit(2).execute()
    print("Loans Table headers:", res.data[0].keys() if res.data else "No data")
    print("Loans:", res.data)
except Exception as e:
    print(e)
