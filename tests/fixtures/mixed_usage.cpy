      *> One field per USAGE family: BINARY, PACKED-DECIMAL, zoned decimal
      *> past 18 digits, and both floating-point sizes.
       01  FINANCIAL-RECORD.
           05  RECORD-ID           PIC 9(5)        COMP.
           05  TRANSACTION-COUNT   PIC S9(9)       COMP-3.
           05  UNIT-PRICE          PIC S9(9)V99    COMP-3.
           05  LARGE-ID            PIC S9(18)      COMP.
           05  HUGE-VALUE          PIC S9(20).
           05  SENSOR-READING      COMP-1.
           05  PRECISE-READING     COMP-2.
