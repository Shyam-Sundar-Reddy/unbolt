      *> Three levels of nesting: record -> header group -> date group.
       01  ORDER-RECORD.
           05  ORDER-HEADER.
               10  ORDER-ID        PIC 9(8).
               10  ORDER-DATE.
                   15  ORDER-YEAR  PIC 9(4).
                   15  ORDER-MONTH PIC 9(2).
                   15  ORDER-DAY   PIC 9(2).
           05  ORDER-TOTAL         PIC S9(7)V99.
