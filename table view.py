import sqlite3

# Connect to the database
conn = sqlite3.connect('parking.db')
c = conn.cursor()

# Delete all records from the parking_logs table
c.execute('DELETE FROM parking_logs')

# Commit and close the connection
conn.commit()
conn.close()

print("All entries from 'parking_logs' have been deleted.")
