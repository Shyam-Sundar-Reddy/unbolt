      *> Fixed-repetition table: OCCURS 5 TIMES, no DEPENDING ON.
       01  INVENTORY-RECORD.
           05  WAREHOUSE-ID        PIC 9(4).
           05  ITEM-COUNT          PIC 9(2).
           05  ITEM-TABLE OCCURS 5 TIMES.
               10  ITEM-SKU        PIC X(10).
               10  ITEM-QTY        PIC 9(4).
